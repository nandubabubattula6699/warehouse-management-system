import hmac as _hmac
import os
from contextlib import asynccontextmanager
from typing import Optional, List

import httpx
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, distinct

from app.database import get_db, require_current_schema, SessionLocal
from app.models import InventoryItem, StockMovement, WarehouseUser, InboundShipment, InboundShipmentItem
from app.llm_parser import parse_inbound_documents, DocumentParserError
from app.auth import (
    SESSION_COOKIE_NAME, hash_password, verify_password,
    get_optional_user, require_user, require_supervisor, require_admin
)
from app.inventory_slots import ACTIVE_SLOT_CONFLICT_MESSAGE, ACTIVE_SLOT_INDEX
from app.location_engine import _norm_coord, build_location_info, seed_locations_if_empty
from app.schemas import (
    ItemCreate, ItemUpdatePayload, ItemResponse, StockAdjustPayload, SetQuantityPayload, WarehouseStats,
    SheetSubmitPayload, BulkDeletePayload, StyleRenamePayload,
    ReceivingPayload,
    InboundShipmentCreate,
    InboundShipmentResponse, InboundParseRequest, InboundApprovePayload, InboundRejectPayload
)

# Route-level access rules (server-side; the frontend's hidden buttons are not security).
LOGIN_REQUIRED = [Depends(require_user)]        # any approved, logged-in user
SUPERVISOR_ONLY = [Depends(require_supervisor)]  # ADMIN or MANAGER
ADMIN_ONLY = [Depends(require_admin)]

# Deactivated inventory rows (is_active = false) keep their stock history but are hidden from every
# stock view, lookup, map, export and the picking service. They are never matched for new stock.
ACTIVE_ITEM = InventoryItem.is_active.is_(True)


def _integrity_message(exc: IntegrityError) -> str:
    """User-facing text for a database constraint violation (nothing was saved)."""
    if ACTIVE_SLOT_INDEX in str(getattr(exc, "orig", exc)):
        return ACTIVE_SLOT_CONFLICT_MESSAGE
    return "The change conflicts with existing data (database constraint) and was not saved."

def seed_if_empty():
    """
    Check the schema is at the latest Alembic migration (refuse to start otherwise) and seed the
    location master list if it is empty. Never creates/alters tables (that is `alembic upgrade head`)
    and NEVER inserts, deletes, or modifies inventory rows. Loading inventory from CSV is a
    manual, explicit operation (scripts/migrate_inventory.py).
    """
    revision = require_current_schema()
    print(f"[Database] Schema at migration {revision}.", flush=True)
    try:
        db_map = SessionLocal()
        try:
            seed_locations_if_empty(db_map)
        finally:
            db_map.close()

        db = SessionLocal()
        try:
            count = db.query(func.count(InventoryItem.id)).scalar() or 0
        finally:
            db.close()
        if count == 0:
            print("[Database] WARNING: inventory_items is EMPTY. Not auto-seeding. "
                  "Check DATABASE_URL points at the right database.", flush=True)
        else:
            print(f"[Database] {count:,} inventory records present.", flush=True)
    except Exception as e:
        print(f"[Database Startup Warning]: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import importlib.util
    import subprocess
    import sys
    seed_if_empty()
    child_procs = []
    services_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services"))
    main_port = os.environ.get("PORT", "8000")

    local_services = [
        ("picking-service", "PICKING_SERVICE_URL", 8001, "segno"),
        ("vision-llm-service", "VISION_SERVICE_URL", 8002, "rapidocr_onnxruntime"),
    ]
    for folder, url_env, port, check_mod in local_services:
        svc_dir = os.path.join(services_root, folder)
        if not os.getenv(url_env) and os.path.isdir(svc_dir) and importlib.util.find_spec(check_mod):
            try:
                env = os.environ.copy()
                env.setdefault("INVENTORY_SERVICE_URL", f"http://127.0.0.1:{main_port}")
                # INTERNAL_API_KEY / PICK_DEVICE_TOKENS are inherited from this process's env; no defaults.
                proc = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                    cwd=svc_dir,
                    env=env,
                )
                child_procs.append(proc)
                print(f"[Gateway] Started local {folder} microservice on 127.0.0.1:{port}", flush=True)
            except Exception as e:
                print(f"[Gateway] Note: could not auto-start local {folder}: {e}", flush=True)
    try:
        yield
    finally:
        for proc in child_procs:
            if proc.poll() is None:
                proc.terminate()


app = FastAPI(
    lifespan=lifespan,
    title="Warehouse Inventory OS - Manager Multi-Style View",
    description="Multi-style tracking, location mapping, and live stock adjustments in PostgreSQL.",
    version="2.1.0"
)


@app.exception_handler(IntegrityError)
async def _integrity_error_to_409(request: Request, exc: IntegrityError):
    # e.g. a second active row for the same slot (create, edit, reactivate, rename, receiving).
    # The request's session is rolled back and closed by get_db; nothing was saved.
    return JSONResponse(status_code=409, content={"detail": _integrity_message(exc)})

def _allowed_origins() -> List[str]:
    """
    Cross-origin browser access is allowed ONLY for origins listed in ALLOWED_ORIGINS
    (comma-separated, e.g. "https://alexander-warehouse.up.railway.app"). Wildcards are rejected.
    Empty/unset = no cross-origin access at all (the app's own pages are same-origin and unaffected).
    """
    origins = []
    for raw in (os.getenv("ALLOWED_ORIGINS") or "").split(","):
        o = raw.strip().rstrip("/")
        if not o:
            continue
        if o == "*" or not o.startswith(("https://", "http://")):
            raise RuntimeError(f"ALLOWED_ORIGINS entry '{o}' is invalid: use full origins like https://example.com, no '*'.")
        origins.append(o)
    return origins


ALLOWED_ORIGINS = _allowed_origins()
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Device-Token"],
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "PostgreSQL"}

@app.get("/api/stats", response_model=WarehouseStats, dependencies=LOGIN_REQUIRED)
def get_stats(db: Session = Depends(get_db)):
    total_styles = db.query(func.count(distinct(InventoryItem.style))).filter(ACTIVE_ITEM).scalar() or 0
    total_records = db.query(func.count(InventoryItem.id)).filter(ACTIVE_ITEM).scalar() or 0
    total_units = db.query(func.sum(InventoryItem.quantity)).filter(ACTIVE_ITEM).scalar() or 0
    total_locations = db.query(func.count(distinct(InventoryItem.location))).filter(ACTIVE_ITEM).scalar() or 0

    return WarehouseStats(
        total_styles=total_styles,
        total_records=total_records,
        total_units=int(total_units),
        total_locations=total_locations
    )

@app.get("/api/styles", dependencies=LOGIN_REQUIRED)
def list_styles(
    q: Optional[str] = Query(None, description="Search style code e.g. A12"),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db)
):
    query = db.query(
        InventoryItem.style,
        func.sum(InventoryItem.quantity).label("total_qty"),
        func.count(InventoryItem.id).label("location_count")
    ).filter(ACTIVE_ITEM)
    if q:
        query = query.filter(InventoryItem.style.ilike(f"%{q.strip()}%"))

    results = query.group_by(InventoryItem.style).order_by(InventoryItem.style.asc()).limit(limit).all()

    return [
        {
            "style": r[0],
            "total_quantity": int(r[1] or 0),
            "location_count": int(r[2] or 0)
        }
        for r in results
    ]


def _parse_num_or_inf(val, special_map=None) -> float:
    if val is None:
        return 999999.0
    s = str(val).strip().upper()
    if not s:
        return 999999.0
    if special_map and s in special_map:
        return float(special_map[s])
    try:
        return float(s)
    except Exception:
        import re as _re
        m = _re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 999998.0


_SIZE_ORDER_MAP = {
    "XXS": 1, "XS": 2, "S": 3, "SM": 3, "M": 4, "MD": 4,
    "L": 5, "LG": 5, "XL": 6, "XXL": 7, "2XL": 7, "3XL": 8, "OS": 900, "ONE SIZE": 900
}
_SECTION_SPECIAL_MAP = {"FRONT": -3, "BACK": -2, "WALL": -1}
_ROW_SPECIAL_MAP = {"WALL": 999}


def sort_inventory_items_physically(items):
    """
    Sort items in exact physical warehouse order:
      - Part 1 (Allbirds): Line (1..14) -> Section (1..35) -> Level (1..4) -> Color -> Size (numeric 5..14)
      - Part 2 (VD/Valentino): Row (1..14, WALL) -> Section (FRONT, BACK, 1..36) -> Level (1..4) -> Color -> Size
    """
    def _sort_key(it):
        part = getattr(it, "warehouse_part", None) or ("PART_2" if (getattr(it, "row_pos", None) and not getattr(it, "line", None)) else "PART_1")
        part_ord = 1 if part == "PART_1" else 2
        if part == "PART_1":
            aisle_num = _parse_num_or_inf(getattr(it, "line", None))
            aisle_str = str(getattr(it, "line", "") or "")
        else:
            aisle_num = _parse_num_or_inf(getattr(it, "row_pos", None), _ROW_SPECIAL_MAP)
            aisle_str = str(getattr(it, "row_pos", "") or "")

        sec_num = _parse_num_or_inf(getattr(it, "section", None), _SECTION_SPECIAL_MAP)
        sec_str = str(getattr(it, "section", "") or "")
        lvl_num = _parse_num_or_inf(getattr(it, "level", None))
        lvl_str = str(getattr(it, "level", "") or "")
        color_str = str(getattr(it, "color", "") or "STANDARD").strip().upper()
        size_num = _parse_num_or_inf(getattr(it, "size", None), _SIZE_ORDER_MAP)
        size_str = str(getattr(it, "size", "") or "").strip().upper()
        style_str = str(getattr(it, "style", "") or "").strip().upper()

        return (part_ord, aisle_num, aisle_str, sec_num, sec_str, lvl_num, lvl_str, color_str, size_num, size_str, style_str)

    return sorted(items, key=_sort_key)

# Multi-Style Batch Lookup Endpoint
@app.get("/api/styles-batch", dependencies=LOGIN_REQUIRED)
def get_styles_batch(
    styles: str = Query(..., description="Comma or space-separated style codes e.g. A12501,A12856"),
    db: Session = Depends(get_db)
):
    # Split by comma first so style names containing spaces (e.g. "VDSW-2092 SND") stay intact
    raw_list = [s.strip().upper() for s in styles.split(",") if s.strip()]
    if not raw_list:
        raise HTTPException(status_code=400, detail="No styles provided")

    no_space_list = [s.replace(" ", "") for s in raw_list]
    match_clauses = [
        func.upper(InventoryItem.style).in_(raw_list),
        func.replace(func.upper(InventoryItem.style), " ", "").in_(no_space_list),
    ]
    for tok in raw_list:
        if tok.startswith("LINE ") or tok.startswith("LINE-") or tok.startswith("LINE#") or (tok.startswith("LINE") and tok[4:].strip().isdigit()):
            ln_val = tok.replace("LINE#", "").replace("LINE-", "").replace("LINE", "").strip()
            if ln_val:
                match_clauses.append(func.upper(func.coalesce(InventoryItem.line, "")) == ln_val)
        elif tok.startswith("ROW ") or tok.startswith("ROW-") or tok.startswith("ROW#") or (tok.startswith("ROW") and tok[3:].strip()):
            rw_val = tok.replace("ROW#", "").replace("ROW-", "").replace("ROW", "").strip()
            if rw_val:
                match_clauses.append(func.upper(func.coalesce(InventoryItem.row_pos, "")) == rw_val)
        elif tok in ("WALL", "WALL ZONE"):
            match_clauses.append(func.upper(func.coalesce(InventoryItem.row_pos, "")) == "WALL")
            match_clauses.append(func.upper(func.coalesce(InventoryItem.section, "")) == "WALL")
        elif tok.isdigit() and int(tok) in range(1, 16):
            match_clauses.append(func.upper(func.coalesce(InventoryItem.line, "")) == tok)
            match_clauses.append(func.upper(func.coalesce(InventoryItem.row_pos, "")) == tok)
            match_clauses.append(func.upper(InventoryItem.style).like(f"{tok}%"))
        else:
            match_clauses.append(func.upper(InventoryItem.style).like(f"{tok}%"))

    items = db.query(InventoryItem).filter(
        ACTIVE_ITEM, or_(*match_clauses)
    ).all()
    items = sort_inventory_items_physically(items)

    if not items:
        raise HTTPException(status_code=404, detail="None of the requested styles were found in PostgreSQL.")

    total_qty = sum(i.quantity for i in items)
    found_styles = sorted(list(set(i.style for i in items)))

    per_style = {}
    for s in found_styles:
        s_items = [i for i in items if i.style.upper() == s.upper()]
        per_style[s] = {
            "style": s,
            "total_quantity": sum(i.quantity for i in s_items),
            "total_locations": len(set(i.location for i in s_items)),
            "sizes": sorted(list(set(i.size for i in s_items if i.size))),
            "colors": sorted(list(set(i.color for i in s_items if i.color)))
        }

    return {
        "requested_styles": raw_list,
        "found_styles": found_styles,
        "total_quantity": total_qty,
        "total_records": len(items),
        "per_style": per_style,
        "items": [ItemResponse.model_validate(i) for i in items]
    }

@app.get("/api/styles/{style_code}", dependencies=LOGIN_REQUIRED)
def get_style_detail(style_code: str, db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(
        ACTIVE_ITEM, InventoryItem.style.ilike(style_code.strip())
    ).order_by(InventoryItem.line.asc(), InventoryItem.section.asc(), InventoryItem.size.asc()).all()

    if not items:
        raise HTTPException(status_code=404, detail=f"Style '{style_code}' not found")

    total_qty = sum(i.quantity for i in items)
    unique_locations = sorted(list(set(i.location for i in items if i.location)))
    unique_sizes = sorted(list(set(i.size for i in items if i.size)))
    unique_colors = sorted(list(set(i.color for i in items if i.color)))

    return {
        "style": items[0].style,
        "total_quantity": total_qty,
        "total_locations": len(unique_locations),
        "sizes": unique_sizes,
        "colors": unique_colors,
        "items": [ItemResponse.model_validate(i) for i in items]
    }

def _actor_name(user: WarehouseUser) -> str:
    """Name written to stock_movements.staff_name: the LOGGED-IN user, never a client-typed name."""
    return ((user.full_name or "").strip() or user.username)[:100]


def _require_active(item: InventoryItem) -> None:
    if not item.is_active:
        raise HTTPException(
            status_code=409,
            detail=f"{item.style} at {item.location} is deactivated. Reactivate it on the Manage page first.",
        )


@app.post("/api/items/{item_id}/adjust", response_model=ItemResponse)
def adjust_quantity(
    item_id: int,
    payload: StockAdjustPayload,
    db: Session = Depends(get_db),
    user: WarehouseUser = Depends(require_supervisor),
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    _require_active(item)

    new_qty = item.quantity + payload.change_amount
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"Stock cannot be negative. Current stock is {item.quantity}.")

    item.quantity = new_qty

    m = StockMovement(
        item_id=item.id,
        style=item.style,
        change_amount=payload.change_amount,
        quantity_after=new_qty,
        movement_type=payload.movement_type or ("STOCK_IN" if payload.change_amount > 0 else "STOCK_OUT"),
        reason=payload.reason or ("Quick Add" if payload.change_amount > 0 else "Quick Deduct"),
        staff_name=_actor_name(user),
    )
    db.add(m)
    db.commit()
    db.refresh(item)
    return item

@app.post("/api/items/{item_id}/set-quantity", response_model=ItemResponse)
def set_quantity(
    item_id: int,
    payload: SetQuantityPayload,
    db: Session = Depends(get_db),
    user: WarehouseUser = Depends(require_supervisor),
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    _require_active(item)

    if payload.new_quantity < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative.")

    delta = payload.new_quantity - item.quantity
    item.quantity = payload.new_quantity

    m = StockMovement(
        item_id=item.id,
        style=item.style,
        change_amount=delta,
        quantity_after=payload.new_quantity,
        movement_type="SET_EXACT",
        reason=payload.reason or "Direct Quantity Update",
        staff_name=_actor_name(user),
    )
    db.add(m)
    db.commit()
    db.refresh(item)
    return item

@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED, dependencies=SUPERVISOR_ONLY)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    info = build_location_info(
        style=data["style"],
        line=data.get("line"),
        section=data.get("section"),
        level=data.get("level"),
        row_pos=data.get("row_pos"),
        box_num=data.get("box_num"),
    )
    data.update({
        "style": data["style"].strip().upper(),
        "brand": info["brand"],
        "warehouse_part": info["warehouse_part"],
        "placement_type": info["placement_type"],
        "location_code": info["location_code"],
        "location": info["location"],
        "line": info["line"],
        "row_pos": info["row_pos"],
        "section": info["section"],
        "level": info["level"],
        "box_num": info["box_num"],
    })
    new_item = InventoryItem(**data)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    if new_item.quantity > 0:
        m = StockMovement(
            item_id=new_item.id,
            style=new_item.style,
            change_amount=new_item.quantity,
            quantity_after=new_item.quantity,
            movement_type="NEW_ENTRY",
            reason="Added new inventory location",
            staff_name="Manager"
        )
        db.add(m)
        db.commit()

    return new_item

def _never_delete_message(label: str, qty: int) -> str:
    """Inventory rows are never hard-deleted by the app: a delete would remove stock (and a row without
    history) with no recorded movement. Deactivate keeps the row and records who hid it."""
    how = (f"It still has {qty} pcs: bring it to 0 first with 'Adj' (with a reason) or edit it on the Manage "
           f"page and Save with quantity 0, so the stock-out is recorded. Then deactivate it."
           if qty else "It is at 0 pcs, so it can be deactivated now.")
    return (f"{label} cannot be deleted: inventory rows are never deleted, so every stock change stays on "
            f"record. Deactivate it instead: this hides it from all stock views and keeps its history. {how}")


def _set_active(item_id: int, active: bool, db: Session, user: WarehouseUser) -> InventoryItem:
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.is_active == active:
        return item
    if not active and item.quantity != 0:
        raise HTTPException(
            status_code=409,
            detail=(f"{item.style} at {item.location} still has {item.quantity} pcs. Bring it to 0 first "
                    f"('Adj' or Save with quantity 0) so the stock-out is recorded, then deactivate."),
        )
    item.is_active = active
    db.add(StockMovement(
        item_id=item.id,
        style=item.style,
        change_amount=0,
        quantity_after=item.quantity,
        movement_type="REACTIVATE" if active else "DEACTIVATE",
        reason="Row reactivated" if active else "Row deactivated (hidden, history kept)",
        staff_name=_actor_name(user),
    ))
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/items/{item_id}/deactivate", response_model=ItemResponse)
def deactivate_item(item_id: int, db: Session = Depends(get_db), user: WarehouseUser = Depends(require_supervisor)):
    """Soft-delete: hide a quantity-0 row from every stock view while keeping its movement history."""
    return _set_active(item_id, False, db, user)


@app.post("/api/items/{item_id}/reactivate", response_model=ItemResponse)
def reactivate_item(item_id: int, db: Session = Depends(get_db), user: WarehouseUser = Depends(require_supervisor)):
    return _set_active(item_id, True, db, user)


@app.delete("/api/items/{item_id}", dependencies=SUPERVISOR_ONLY)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    raise HTTPException(status_code=409, detail=_never_delete_message(f"{item.style} at {item.location}",
                                                                      item.quantity))

@app.get("/api/movements", dependencies=LOGIN_REQUIRED)
def get_movements(limit: int = 50, db: Session = Depends(get_db)):
    movements = (
        db.query(StockMovement, InventoryItem.location, InventoryItem.size, InventoryItem.color)
        .join(InventoryItem, StockMovement.item_id == InventoryItem.id)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "style": m.style,
            "location": loc,
            "size": sz,
            "color": col,
            "change_amount": m.change_amount,
            "quantity_after": m.quantity_after,
            "movement_type": m.movement_type,
            "reason": m.reason,
            "staff_name": m.staff_name,
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        for m, loc, sz, col in movements
    ]


def _clean_str(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _build_location(line, section, level, row_pos, box_num, style: str = "") -> str:
    return build_location_info(style, line, section, level, row_pos, box_num)["location"]


@app.post("/api/sheet-submit", dependencies=SUPERVISOR_ONLY)
def submit_manager_sheet(payload: SheetSubmitPayload, db: Session = Depends(get_db)):
    """
    Process a Manager Sheet (10-25 rows or 1,000+ rows from CSV):
    Supports per-row actions:
      - IN: Add pieces to existing location or create new style/location
      - OUT: Deduct pieces from matching location
      - SET: Set exact pieces at location (or create if new)
      - DELETE: refused (409, sheet not saved): rows are never deleted; use SET 0, then Deactivate
    """
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided in sheet.")

    # Pre-check which styles already exist in DB before this sheet
    all_existing_styles = {
        r[0].upper() for r in db.query(InventoryItem.style).filter(ACTIVE_ITEM).distinct().all() if r[0]
    }

    inserted_count = 0
    updated_count = 0
    deleted_count = 0
    total_pieces_in = 0
    total_pieces_out = 0
    total_cartons = 0
    existing_styles_in_sheet = set()
    new_styles_in_sheet = set()
    touched_styles = []
    staff = (payload.staff_name or "Nandu").strip()
    note = (payload.sheet_note or "Manager Sheet").strip()

    try:
        for idx, raw in enumerate(payload.rows, start=1):
            style = (_clean_str(raw.style) or "").upper()
            if not style:
                continue
            action = (raw.action or "IN").strip().upper()
            color = (_clean_str(raw.color) or "STANDARD").upper()
            size = (_clean_str(raw.size) or "OS").upper()
            loc_meta = build_location_info(
                style=style,
                line=_clean_str(raw.line),
                section=_clean_str(raw.section),
                level=_clean_str(raw.level),
                row_pos=_clean_str(raw.row_pos),
                box_num=_clean_str(raw.box_num),
            )
            line = loc_meta["line"]
            section = loc_meta["section"]
            level = loc_meta["level"]
            row_pos = loc_meta["row_pos"]
            box_num = loc_meta["box_num"]
            pcs_per_box = raw.pcs_per_box if (raw.pcs_per_box and raw.pcs_per_box > 0) else None
            qty = int(raw.quantity or 0)

            # Track carton count if box_num is numeric
            if box_num and box_num.isdigit():
                total_cartons += int(box_num)
            else:
                total_cartons += 1

            if style in all_existing_styles:
                existing_styles_in_sheet.add(style)
            else:
                new_styles_in_sheet.add(style)
            if style not in touched_styles:
                touched_styles.append(style)

            loc_str = _build_location(line, section, level, row_pos, box_num, style)

            # Find matching record at this location
            q = db.query(InventoryItem).filter(
                ACTIVE_ITEM,
                func.upper(InventoryItem.style) == style,
                func.upper(func.coalesce(InventoryItem.color, "STANDARD")) == color,
                func.upper(func.coalesce(InventoryItem.size, "OS")) == size,
                func.coalesce(InventoryItem.line, "") == (line or ""),
                func.coalesce(InventoryItem.section, "") == (section or ""),
                func.coalesce(InventoryItem.level, "") == (level or ""),
                func.coalesce(InventoryItem.row_pos, "") == (row_pos or ""),
            )
            if box_num:
                exact_match = q.filter(func.coalesce(InventoryItem.box_num, "") == box_num).first()
            else:
                exact_match = q.first()

            if action == "DELETE":
                target = exact_match or q.first()
                if not target:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row #{idx} ({style} at {loc_str}): Location not found to delete."
                    )
                raise HTTPException(
                    status_code=409,
                    detail=f"Row #{idx}: " + _never_delete_message(f"{style} at {target.location}", target.quantity)
                    + " On a sheet, use SET with quantity 0. Sheet not saved.",
                )

            if action == "OUT":
                # Deduct stock from matching location (or across matching locations for that style/color/size)
                target = exact_match or q.order_by(InventoryItem.quantity.desc()).first()
                if not target:
                    # Fallback: if manager only gave style + color + size without exact row/box
                    fallback_q = db.query(InventoryItem).filter(
                        ACTIVE_ITEM,
                        func.upper(InventoryItem.style) == style,
                        func.upper(func.coalesce(InventoryItem.color, "STANDARD")) == color,
                        func.upper(func.coalesce(InventoryItem.size, "OS")) == size,
                    )
                    if line:
                        fallback_q = fallback_q.filter(func.coalesce(InventoryItem.line, "") == line)
                    if section:
                        fallback_q = fallback_q.filter(func.coalesce(InventoryItem.section, "") == section)
                    target = fallback_q.order_by(InventoryItem.quantity.desc()).first()

                if not target:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row #{idx}: Style '{style}' ({color}, Size {size}) at {loc_str} was not found in inventory."
                    )
                if target.quantity < qty:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row #{idx}: Not enough stock for '{style}' at {target.location} (Has {target.quantity} pcs, tried to deduct {qty} pcs)."
                    )
                target.quantity -= qty
                updated_count += 1
                total_pieces_out += qty
                db.add(StockMovement(
                    item_id=target.id,
                    style=target.style,
                    change_amount=-qty,
                    quantity_after=target.quantity,
                    movement_type="SHEET_OUT",
                    reason=f"{note} (Stock OUT)",
                    staff_name=staff,
                ))
                continue

            # Action is IN or SET
            if exact_match:
                if action == "IN":
                    delta = qty
                    exact_match.quantity += qty
                    total_pieces_in += qty
                else:  # SET
                    delta = qty - exact_match.quantity
                    exact_match.quantity = qty
                    if delta >= 0:
                        total_pieces_in += delta
                    else:
                        total_pieces_out += abs(delta)

                if pcs_per_box is not None:
                    exact_match.pcs_per_box = pcs_per_box
                if box_num is not None:
                    exact_match.box_num = box_num
                loc_meta_upd = build_location_info(style, line, section, level, row_pos, exact_match.box_num)
                exact_match.brand = loc_meta_upd["brand"]
                exact_match.warehouse_part = loc_meta_upd["warehouse_part"]
                exact_match.placement_type = loc_meta_upd["placement_type"]
                exact_match.location_code = loc_meta_upd["location_code"]
                exact_match.location = loc_meta_upd["location"]
                updated_count += 1
                db.add(StockMovement(
                    item_id=exact_match.id,
                    style=exact_match.style,
                    change_amount=delta,
                    quantity_after=exact_match.quantity,
                    movement_type="SHEET_IN" if action == "IN" else "SHEET_SET",
                    reason=f"{note} ({'Added to existing bin' if action == 'IN' else 'Updated exact count'})",
                    staff_name=staff,
                ))
            else:
                loc_meta = build_location_info(style, line, section, level, row_pos, box_num)
                new_item = InventoryItem(
                    style=style,
                    brand=loc_meta["brand"],
                    warehouse_part=loc_meta["warehouse_part"],
                    placement_type=loc_meta["placement_type"],
                    location_code=loc_meta["location_code"],
                    color=color,
                    size=size,
                    line=loc_meta["line"],
                    section=loc_meta["section"],
                    level=loc_meta["level"],
                    row_pos=loc_meta["row_pos"],
                    box_num=loc_meta["box_num"],
                    location=loc_meta["location"],
                    pcs_per_box=pcs_per_box,
                    quantity=qty,
                )
                new_item.movements.append(StockMovement(
                    style=new_item.style,
                    change_amount=qty,
                    quantity_after=new_item.quantity,
                    movement_type="NEW_LOCATION_IN",
                    reason=f"{note} (New location entry)",
                    staff_name=staff,
                ))
                db.add(new_item)
                if new_item.warehouse_part == "PART_2":
                    # Part 2 has one active row per slot: later rows of this same sheet must find (and
                    # add to) this new row. Part 1 (Lines) is left exactly as before: one row per carton.
                    db.flush()
                inserted_count += 1
                total_pieces_in += qty

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=_integrity_message(e) + " Sheet not saved.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Sheet failed and rolled back safely: {e}")

    return {
        "status": "ok",
        "processed_rows": len(payload.rows),
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "deleted_count": deleted_count,
        "total_pieces_in": total_pieces_in,
        "total_pieces_out": total_pieces_out,
        "total_cartons": total_cartons,
        "existing_styles_count": len(existing_styles_in_sheet),
        "new_styles_count": len(new_styles_in_sheet),
        "existing_styles": sorted(list(existing_styles_in_sheet)),
        "new_styles": sorted(list(new_styles_in_sheet)),
        "touched_styles": touched_styles,
    }


@app.get("/api/location-search", dependencies=SUPERVISOR_ONLY)
def search_locations(
    style: Optional[str] = Query(None),
    line: Optional[str] = Query(None),
    row_pos: Optional[str] = Query(None),
    warehouse_part: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    include_inactive: bool = Query(False, description="Also return deactivated rows (to reactivate them)"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Search inventory records by style and/or warehouse location coordinates for editing or deleting."""
    q = db.query(InventoryItem)
    if not include_inactive:
        q = q.filter(ACTIVE_ITEM)
    if style and style.strip():
        s_clean = style.strip().upper()
        q = q.filter(
            or_(
                func.upper(InventoryItem.style).contains(s_clean),
                func.replace(func.upper(InventoryItem.style), " ", "").contains(s_clean.replace(" ", ""))
            )
        )
    if warehouse_part and warehouse_part.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.warehouse_part, "")) == warehouse_part.strip().upper())
    if line and line.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.line, "")) == line.strip().upper())
    if row_pos and row_pos.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.row_pos, "")) == row_pos.strip().upper())
    if section and section.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.section, "")).contains(section.strip().upper()))
    if level and level.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.level, "")) == level.strip().upper())
    if color and color.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.color, "")).contains(color.strip().upper()))

    items = q.order_by(
        InventoryItem.style.asc(),
        InventoryItem.line.asc(),
        InventoryItem.section.asc(),
        InventoryItem.level.asc(),
        InventoryItem.size.asc()
    ).limit(limit).all()

    return [ItemResponse.model_validate(i) for i in items]


@app.put("/api/items/{item_id}", response_model=ItemResponse)
def update_item_full(
    item_id: int,
    payload: ItemUpdatePayload,
    db: Session = Depends(get_db),
    user: WarehouseUser = Depends(require_supervisor),
):
    """Edit any field of an inventory row (style, color, size, line, section, level, row, box/cartons, quantity)."""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Location record not found.")
    _require_active(item)
    if payload.quantity < 0:
        raise HTTPException(status_code=400, detail="Quantity cannot be negative.")

    delta = payload.quantity - item.quantity
    old_loc = item.location
    old_style = item.style

    item.style = payload.style.strip().upper()
    item.color = (payload.color or "STANDARD").strip().upper()
    item.size = (payload.size or "OS").strip().upper()
    item.line = _clean_str(payload.line)
    item.section = _clean_str(payload.section)
    item.level = _clean_str(payload.level)
    item.row_pos = _clean_str(payload.row_pos)
    item.box_num = _clean_str(payload.box_num)
    item.pcs_per_box = payload.pcs_per_box
    item.quantity = payload.quantity
    loc_meta = build_location_info(item.style, item.line, item.section, item.level, item.row_pos, item.box_num)
    item.brand = loc_meta["brand"]
    item.warehouse_part = loc_meta["warehouse_part"]
    item.placement_type = loc_meta["placement_type"]
    item.location_code = loc_meta["location_code"]
    item.location = loc_meta["location"]

    db.add(StockMovement(
        item_id=item.id,
        style=item.style,
        change_amount=delta,
        quantity_after=item.quantity,
        movement_type="ROW_EDIT",
        reason=f"Edited row ({old_style} @ {old_loc} -> {item.style} @ {item.location})",
        staff_name=_actor_name(user),
    ))
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/items/bulk-delete", dependencies=SUPERVISOR_ONLY)
def bulk_delete_items(payload: BulkDeletePayload, db: Session = Depends(get_db)):
    """Refused: inventory rows are never deleted. Kept as an endpoint so older pages get a clear 409."""
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="No item IDs selected.")
    raise HTTPException(
        status_code=409,
        detail=("Nothing was deleted: inventory rows are never deleted, so every stock change stays on record. "
                "Use Deactivate on each row instead (a row must be at quantity 0 first: edit and Save with 0, "
                "which records the stock-out)."),
    )


@app.post("/api/styles/rename", dependencies=SUPERVISOR_ONLY)
def rename_style(payload: StyleRenamePayload, db: Session = Depends(get_db)):
    """Rename or merge a wrong style code (e.g. 11159 -> A11159) across all locations."""
    old_s = payload.old_style.strip().upper()
    new_s = payload.new_style.strip().upper()
    if not old_s or not new_s:
        raise HTTPException(status_code=400, detail="Both old and new style codes are required.")
    items = db.query(InventoryItem).filter(func.upper(InventoryItem.style) == old_s).all()
    if not items:
        raise HTTPException(status_code=404, detail=f"Style '{old_s}' not found in PostgreSQL.")
    for item in items:
        item.style = new_s
    db.query(StockMovement).filter(func.upper(StockMovement.style) == old_s).update(
        {"style": new_s}, synchronize_session=False
    )
    db.commit()
    return {"status": "ok", "old_style": old_s, "new_style": new_s, "updated_records": len(items)}


@app.get("/api/export-csv")
def export_inventory_csv(
    include_inactive: bool = Query(False, description="ADMIN only: also export deactivated rows (audits)"),
    db: Session = Depends(get_db),
    user: WarehouseUser = Depends(require_supervisor),
):
    """Export active inventory rows as CSV. Admins can add deactivated rows (extra ACTIVE column)."""
    import csv
    import io
    if include_inactive and (user.role or "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can export deactivated rows.")
    q = db.query(InventoryItem)
    if not include_inactive:
        q = q.filter(ACTIVE_ITEM)
    items = q.order_by(InventoryItem.style.asc(), InventoryItem.line.asc(), InventoryItem.section.asc()).all()
    out = io.StringIO()
    writer = csv.writer(out)
    header = ["SKU", "COLOR", "ROW", "LINE", "SECTION", "LEVEL", "SIZE", "PCS/BOX", "QTY", "BOX #"]
    writer.writerow(header + (["ACTIVE"] if include_inactive else []))
    for i in items:
        row = [
            i.style, i.color or "", i.row_pos or "", i.line or "",
            i.section or "", i.level or "", i.size or "",
            i.pcs_per_box if i.pcs_per_box is not None else "",
            i.quantity, i.box_num or ""
        ]
        writer.writerow(row + (["YES" if i.is_active else "NO"] if include_inactive else []))
    out.seek(0)
    filename = "warehouse_inventory_export_incl_deactivated.csv" if include_inactive else "warehouse_inventory_export.csv"
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/warehouse-overview", dependencies=LOGIN_REQUIRED)
def get_warehouse_overview(db: Session = Depends(get_db)):
    """
    Complete 50,000+ sq ft 2-Part Warehouse Map Overview:
      - PART_1: Allbirds Zone (14 Lines, each 32-35 Sections, 4 Levels)
      - PART_2: Von Dutch & Valentino Zone (14 Rows + WALL, 36 Sections + Ground FRONT/BACK + WALL, 4 Levels)
    """
    items = db.query(InventoryItem).filter(ACTIVE_ITEM).all()

    part1_lines = {
        str(i): {
            "line": str(i),
            "occupied_sections": set(),
            "styles": set(),
            "records": 0,
            "units": 0,
        }
        for i in range(1, 15)
    }
    part1_total_units = 0
    part1_total_records = 0
    part1_styles = set()

    part2_rows = {
        str(i): {
            "row": str(i),
            "occupied_sections": set(),
            "styles": set(),
            "brands": set(),
            "rack_units": 0,
            "ground_front_units": 0,
            "ground_back_units": 0,
            "wall_units": 0,
            "records": 0,
            "units": 0,
        }
        for i in list(range(1, 15)) + ["15", "WALL"]
    }
    part2_total_units = 0
    part2_total_records = 0
    part2_styles = set()
    brand_totals = {}
    placement_totals = {"RACK": 0, "GROUND_FRONT": 0, "GROUND_BACK": 0, "WALL": 0}

    for it in items:
        part = it.warehouse_part or ("PART_2" if (it.row_pos and not it.line) else "PART_1")
        br = it.brand or "ALLBIRDS"
        pl = it.placement_type or "RACK"
        qty = it.quantity or 0

        brand_totals[br] = brand_totals.get(br, 0) + qty
        placement_totals[pl] = placement_totals.get(pl, 0) + qty

        if part == "PART_1":
            part1_total_units += qty
            part1_total_records += 1
            part1_styles.add(it.style)
            ln_key = str(it.line or "1").strip()
            if ln_key not in part1_lines:
                part1_lines[ln_key] = {
                    "line": ln_key,
                    "occupied_sections": set(),
                    "styles": set(),
                    "records": 0,
                    "units": 0,
                }
            part1_lines[ln_key]["records"] += 1
            part1_lines[ln_key]["units"] += qty
            part1_lines[ln_key]["styles"].add(it.style)
            if it.section:
                part1_lines[ln_key]["occupied_sections"].add(str(it.section))
        else:
            part2_total_units += qty
            part2_total_records += 1
            part2_styles.add(it.style)
            rw_key = str(it.row_pos or "1").strip().upper()
            if rw_key not in part2_rows:
                part2_rows[rw_key] = {
                    "row": rw_key,
                    "occupied_sections": set(),
                    "styles": set(),
                    "brands": set(),
                    "rack_units": 0,
                    "ground_front_units": 0,
                    "ground_back_units": 0,
                    "wall_units": 0,
                    "records": 0,
                    "units": 0,
                }
            r_obj = part2_rows[rw_key]
            r_obj["records"] += 1
            r_obj["units"] += qty
            r_obj["styles"].add(it.style)
            r_obj["brands"].add(br)
            if it.section:
                r_obj["occupied_sections"].add(str(it.section))
            if pl == "GROUND_FRONT":
                r_obj["ground_front_units"] += qty
            elif pl == "GROUND_BACK":
                r_obj["ground_back_units"] += qty
            elif pl == "WALL":
                r_obj["wall_units"] += qty
            else:
                r_obj["rack_units"] += qty

    part1_list = [
        {
            "line": k,
            "occupied_sections": len(v["occupied_sections"]),
            "max_sections": 35,
            "levels": 4,
            "total_styles": len(v["styles"]),
            "total_records": v["records"],
            "total_units": v["units"],
        }
        for k, v in part1_lines.items()
    ]

    part2_list = [
        {
            "row": k,
            "occupied_sections": len(v["occupied_sections"]),
            "max_sections": 36,
            "levels": 4,
            "brands": sorted(list(v["brands"])),
            "rack_units": v["rack_units"],
            "ground_front_units": v["ground_front_units"],
            "ground_back_units": v["ground_back_units"],
            "wall_units": v["wall_units"],
            "total_styles": len(v["styles"]),
            "total_records": v["records"],
            "total_units": v["units"],
        }
        for k, v in part2_rows.items()
        if k in [str(i) for i in range(1, 15)] + ["WALL"] or v["records"] > 0
    ]

    return {
        "warehouse_sqft": "50,000+ sq ft",
        "part_1_allbirds": {
            "name": "Part 1: Allbirds Zone (14 Lines × 32–35 Sections × 4 Levels)",
            "total_lines": 14,
            "sections_per_line": "32–35",
            "levels_per_section": 4,
            "total_styles": len(part1_styles),
            "total_records": part1_total_records,
            "total_units": part1_total_units,
            "lines": part1_list,
        },
        "part_2_vd_valentino": {
            "name": "Part 2: Von Dutch & Valentino Zone (14 Rows × 36 Sections + Ground FRONT/BACK + WALL × 4 Levels)",
            "total_rows": 14,
            "sections_per_row": "36 + Ground FRONT / BACK / WALL",
            "levels_per_section": 4,
            "total_styles": len(part2_styles),
            "total_records": part2_total_records,
            "total_units": part2_total_units,
            "rows": part2_list,
        },
        "brand_totals": brand_totals,
        "placement_totals": placement_totals,
    }


@app.get("/api/warehouse-map/aisle", dependencies=LOGIN_REQUIRED)
def get_warehouse_aisle_detail(
    part: str = Query(..., description="PART_1 or PART_2"),
    aisle: str = Query(..., description="Line number (1..14) for PART_1, or Row number (1..14 / WALL) for PART_2"),
    db: Session = Depends(get_db)
):
    """
    Return the Section x Level (1..4) breakdown for a specific Line in Part 1 or a specific Row/Wall in Part 2.
    """
    p = part.strip().upper()
    a = aisle.strip().upper()

    if p == "PART_1":
        items = db.query(InventoryItem).filter(
            ACTIVE_ITEM, func.coalesce(InventoryItem.line, "") == a
        ).order_by(InventoryItem.section.asc(), InventoryItem.level.asc(), InventoryItem.style.asc()).all()
    else:
        items = db.query(InventoryItem).filter(
            ACTIVE_ITEM, func.upper(func.coalesce(InventoryItem.row_pos, "")) == a
        ).order_by(InventoryItem.section.asc(), InventoryItem.level.asc(), InventoryItem.style.asc()).all()

    sections_map = {}
    for it in items:
        sec_key = (it.section or "UNASSIGNED").upper()
        lvl_key = str(it.level or "1")
        if sec_key not in sections_map:
            sections_map[sec_key] = {
                "section": sec_key,
                "placement_type": it.placement_type or ("GROUND_FRONT" if sec_key == "FRONT" else ("GROUND_BACK" if sec_key == "BACK" else ("WALL" if a == "WALL" or sec_key == "WALL" else "RACK"))),
                "total_units": 0,
                "total_records": 0,
                "levels": {"1": [], "2": [], "3": [], "4": [], "OTHER": []},
            }
        s_obj = sections_map[sec_key]
        s_obj["total_units"] += (it.quantity or 0)
        s_obj["total_records"] += 1
        target_lvl = lvl_key if lvl_key in ("1", "2", "3", "4") else "OTHER"
        s_obj["levels"][target_lvl].append({
            "id": it.id,
            "style": it.style,
            "brand": it.brand or ("ALLBIRDS" if p == "PART_1" else "VON DUTCH"),
            "color": it.color,
            "size": it.size,
            "box_num": it.box_num,
            "pcs_per_box": it.pcs_per_box,
            "quantity": it.quantity,
            "location": it.location,
        })

    def sec_sort_key(sec_name: str):
        if sec_name == "FRONT":
            return (0, 0, sec_name)
        if sec_name == "BACK":
            return (0, 1, sec_name)
        if sec_name == "WALL":
            return (0, 2, sec_name)
        if sec_name.isdigit():
            return (1, int(sec_name), sec_name)
        return (2, 0, sec_name)

    sorted_sections = [sections_map[k] for k in sorted(sections_map.keys(), key=sec_sort_key)]
    return {
        "part": p,
        "aisle": a,
        "aisle_label": f"Line {a} (Allbirds)" if p == "PART_1" else ("WALL Zone" if a == "WALL" else f"Row {a} (Von Dutch / Valentino)"),
        "total_sections_occupied": len(sorted_sections),
        "total_units": sum(s["total_units"] for s in sorted_sections),
        "total_records": sum(s["total_records"] for s in sorted_sections),
        "sections": sorted_sections,
    }



# ================= AUTHENTICATION & USER ACCESS CONTROL ENDPOINTS =================
class LoginPayload(BaseModel):
    username: str
    password: str


SIGNUP_ROLE = "STAFF"  # lowest role; only an admin can grant more (create the user from the admin panel)
SIGNUP_ZONES = ("ALL_ZONES", "PART_1_ALLBIRDS", "PART_2_VD_VALENTINO")


class SignupPayload(BaseModel):
    full_name: str
    username: str
    email: Optional[str] = None
    password: str
    role: Optional[str] = None  # IGNORED — kept only so older clients don't get a 422
    assigned_zone: Optional[str] = "ALL_ZONES"


class AdminCreateUserPayload(BaseModel):
    full_name: str
    username: str
    email: Optional[str] = None
    password: str
    role: Optional[str] = "STAFF"
    assigned_zone: Optional[str] = "ALL_ZONES"


class AdminUpdateStatusPayload(BaseModel):
    is_approved: int


@app.post("/api/auth/login")
def login_user(payload: LoginPayload, response: Response, db: Session = Depends(get_db)):
    from datetime import datetime
    import secrets
    ident = payload.username.strip().lower()
    user = db.query(WarehouseUser).filter(
        or_(
            func.lower(WarehouseUser.username) == ident,
            func.lower(func.coalesce(WarehouseUser.email, "")) == ident,
        )
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username/email or password.")

    if user.is_approved == 0:
        raise HTTPException(
            status_code=403,
            detail="Your account is pending approval. Please ask Admin (Nandu) to grant you access."
        )
    if user.is_approved < 0:
        raise HTTPException(
            status_code=403,
            detail="Your access to Warehouse OS has been revoked by the Admin."
        )

    token = secrets.token_hex(32)
    user.session_token = token
    user.last_seen_at = datetime.utcnow()
    db.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 14,  # 14 days
        samesite="lax",
    )
    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "assigned_zone": user.assigned_zone,
        }
    }


@app.post("/api/auth/signup")
def signup_user(payload: SignupPayload, db: Session = Depends(get_db)):
    from datetime import datetime
    uname = payload.username.strip().lower()
    if not uname or len(uname) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters.")

    existing = db.query(WarehouseUser).filter(func.lower(WarehouseUser.username) == uname).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{uname}' is already registered.")

    email_clean = payload.email.strip().lower() if payload.email and payload.email.strip() else None
    if email_clean:
        ex_email = db.query(WarehouseUser).filter(func.lower(WarehouseUser.email) == email_clean).first()
        if ex_email:
            raise HTTPException(status_code=400, detail=f"Email '{email_clean}' is already registered.")

    zone = (payload.assigned_zone or "ALL_ZONES").strip().upper()
    new_u = WarehouseUser(
        username=uname,
        email=email_clean,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=SIGNUP_ROLE,  # never taken from the request
        assigned_zone=zone if zone in SIGNUP_ZONES else "ALL_ZONES",
        is_approved=0,  # pending: login is refused until an admin approves
        created_at=datetime.utcnow(),
    )
    db.add(new_u)
    db.commit()
    return {
        "status": "ok",
        "message": f"Sign-up request submitted for '{new_u.full_name}' (@{new_u.username})! Admin (Nandu) can now approve your access in 1 click."
    }


@app.post("/api/auth/logout")
def logout_user(request: Request, response: Response, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if user:
        user.session_token = None
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@app.get("/api/auth/me")
def get_current_user_info(request: Request, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    cutoff = datetime.utcnow() - timedelta(minutes=5)
    online_count = db.query(WarehouseUser).filter(
        WarehouseUser.is_approved == 1,
        WarehouseUser.last_seen_at >= cutoff
    ).count()
    pending_count = db.query(WarehouseUser).filter(WarehouseUser.is_approved == 0).count()

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "assigned_zone": user.assigned_zone,
        },
        "online_users_count": max(1, online_count),
        "pending_users_count": pending_count,
    }


@app.get("/api/admin/users")
def admin_list_users(admin: WarehouseUser = Depends(require_admin), db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    users = db.query(WarehouseUser).order_by(WarehouseUser.is_approved.asc(), WarehouseUser.id.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "assigned_zone": u.assigned_zone,
            "is_approved": u.is_approved,
            "is_online": bool(u.last_seen_at and u.last_seen_at >= cutoff and u.session_token),
            "last_seen_at": u.last_seen_at.strftime("%Y-%m-%d %H:%M:%S") if u.last_seen_at else None,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else None,
        }
        for u in users
    ]


@app.post("/api/admin/users")
def admin_create_approved_user(
    payload: AdminCreateUserPayload,
    admin: WarehouseUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    uname = payload.username.strip().lower()
    if db.query(WarehouseUser).filter(func.lower(WarehouseUser.username) == uname).first():
        raise HTTPException(status_code=400, detail=f"Username '{uname}' already exists.")
    u = WarehouseUser(
        username=uname,
        email=payload.email.strip().lower() if payload.email and payload.email.strip() else None,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=(payload.role or "STAFF").upper(),
        assigned_zone=(payload.assigned_zone or "ALL_ZONES").upper(),
        is_approved=1,  # Directly approved by Admin!
        created_at=datetime.utcnow(),
    )
    db.add(u)
    db.commit()
    return {"status": "ok", "id": u.id, "username": u.username}


@app.post("/api/admin/users/{user_id}/status")
def admin_update_user_status(
    user_id: int,
    payload: AdminUpdateStatusPayload,
    admin: WarehouseUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    u = db.query(WarehouseUser).filter(WarehouseUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.username == "nandu" and payload.is_approved != 1:
        raise HTTPException(status_code=400, detail="Cannot revoke primary Admin account.")
    u.is_approved = payload.is_approved
    if payload.is_approved != 1:
        u.session_token = None
    db.commit()
    return {"status": "ok", "id": u.id, "is_approved": u.is_approved}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    admin: WarehouseUser = Depends(require_admin),
    db: Session = Depends(get_db)
):
    u = db.query(WarehouseUser).filter(WarehouseUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.username == "nandu":
        raise HTTPException(status_code=400, detail="Cannot delete primary Admin account.")
    db.delete(u)
    db.commit()
    return {"status": "ok"}


@app.post("/api/receiving", dependencies=LOGIN_REQUIRED)
def receive_stock(payload: ReceivingPayload, db: Session = Depends(get_db)):
    """
    Dedicated Inbound Stock Receiving Endpoint for Manager & Admin.
    Checks in incoming inventory, creates or merges into shelf location,
    and logs a StockMovement audit record with type 'RECEIVING'.
    """
    style = payload.style.strip().upper()
    if not style:
        raise HTTPException(status_code=400, detail="Style code is required.")
    color = (payload.color or "STANDARD").strip().upper()
    size = (payload.size or "OS").strip().upper()
    line = payload.line.strip() if payload.line and payload.line.strip() else None
    row_pos = payload.row_pos.strip() if payload.row_pos and payload.row_pos.strip() else None
    section = payload.section.strip() if payload.section and payload.section.strip() else None
    level = payload.level.strip() if payload.level and payload.level.strip() else None
    box_num = payload.box_num.strip() if payload.box_num and payload.box_num.strip() else None
    staff = (payload.staff_name or "Warehouse Manager").strip()
    po = (payload.po_number or "").strip()
    notes = (payload.notes or "").strip()
    reason = f"Inbound Receiving PO: {po}" if po else (notes or "Inbound Stock Receiving")

    loc_meta = build_location_info(
        style=style,
        line=line,
        section=section,
        level=level,
        row_pos=row_pos,
        box_num=box_num
    )

    q = db.query(InventoryItem).filter(
        ACTIVE_ITEM,
        func.upper(InventoryItem.style) == style,
        func.upper(func.coalesce(InventoryItem.color, "STANDARD")) == color,
        func.upper(func.coalesce(InventoryItem.size, "OS")) == size,
        func.coalesce(InventoryItem.line, "") == (loc_meta["line"] or ""),
        func.coalesce(InventoryItem.section, "") == (loc_meta["section"] or ""),
        func.coalesce(InventoryItem.level, "") == (loc_meta["level"] or ""),
        func.coalesce(InventoryItem.row_pos, "") == (loc_meta["row_pos"] or ""),
    )
    if loc_meta["box_num"]:
        target = q.filter(func.coalesce(InventoryItem.box_num, "") == loc_meta["box_num"]).first()
    else:
        target = q.first()

    if target:
        target.quantity += payload.quantity
        if payload.pcs_per_box:
            target.pcs_per_box = payload.pcs_per_box
        db.add(StockMovement(
            item_id=target.id,
            style=target.style,
            change_amount=payload.quantity,
            quantity_after=target.quantity,
            movement_type="RECEIVING",
            reason=reason,
            staff_name=staff
        ))
        db.commit()
        db.refresh(target)
        return {
            "status": "success",
            "action": "merged",
            "item": ItemResponse.model_validate(target),
            "message": f"Added {payload.quantity} pcs to existing location {target.location} (New Stock: {target.quantity} pcs)",
            "location": target.location
        }
    else:
        brand = payload.brand or loc_meta["brand"]
        new_item = InventoryItem(
            style=style,
            brand=brand,
            warehouse_part=loc_meta["warehouse_part"],
            placement_type=loc_meta["placement_type"],
            location_code=loc_meta["location_code"],
            location=loc_meta["location"],
            color=color,
            size=size,
            line=loc_meta["line"],
            section=loc_meta["section"],
            level=loc_meta["level"],
            row_pos=loc_meta["row_pos"],
            box_num=loc_meta["box_num"],
            pcs_per_box=payload.pcs_per_box,
            quantity=payload.quantity
        )
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        db.add(StockMovement(
            item_id=new_item.id,
            style=new_item.style,
            change_amount=payload.quantity,
            quantity_after=new_item.quantity,
            movement_type="RECEIVING",
            reason=reason,
            staff_name=staff
        ))
        db.commit()
        return {
            "status": "success",
            "action": "created",
            "item": ItemResponse.model_validate(new_item),
            "message": f"Received {new_item.quantity} pcs at new location {new_item.location}",
            "location": new_item.location
        }


# ================= MULTI-PALLET INBOUND RECEIVING & ADMIN APPROVAL ENDPOINTS =================

@app.post("/api/inbound/parse-docs", dependencies=LOGIN_REQUIRED)
def api_parse_inbound_documents(payload: InboundParseRequest):
    """
    Multimodal AI document reader: Reads photographs/scans of Packing List & Commercial Invoice,
    extracts all products, styles, colors, sizes, box counts, and total pieces.
    """
    try:
        extracted = parse_inbound_documents(
            packing_list_data=payload.packing_list_data,
            commercial_invoice_data=payload.commercial_invoice_data,
            packing_list_filename=payload.packing_list_filename,
            commercial_invoice_filename=payload.commercial_invoice_filename,
            raw_text=payload.raw_text
        )
    except DocumentParserError as e:
        print(f"[Inbound AI] {e.status_code}: {e.message}", flush=True)
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"status": "success", "data": extracted}


@app.post("/api/inbound/shipments", response_model=InboundShipmentResponse, dependencies=LOGIN_REQUIRED)
def create_inbound_shipment(payload: InboundShipmentCreate, db: Session = Depends(get_db)):
    """
    Manager stages and submits a verified inbound shipment (1 to 20 pallets, 8 to 40 boxes/pallet)
    with assigned warehouse shelf locations for Admin Approval.
    """
    from datetime import datetime
    import os

    for n, it in enumerate(payload.items, start=1):
        if not (it.style or "").strip():
            raise HTTPException(status_code=400, detail=f"Line #{n}: style is required.")
        if (it.quantity or 0) < 0:
            raise HTTPException(status_code=400, detail=f"Line #{n} ({it.style}): quantity cannot be negative.")

    shipment_num = payload.shipment_number
    if not shipment_num or not shipment_num.strip():
        date_str = datetime.utcnow().strftime("%Y%m%d")
        rand_hex = os.urandom(2).hex().upper()
        shipment_num = f"SHP-{date_str}-{rand_hex}"

    tot_boxes = sum(i.box_count or 1 for i in payload.items) if payload.items else (payload.total_boxes or 0)
    tot_units = sum(i.quantity or 0 for i in payload.items) if payload.items else (payload.total_units or 0)

    shipment = InboundShipment(
        shipment_number=shipment_num,
        po_number=payload.po_number,
        carrier_vendor=payload.carrier_vendor,
        pallets_count=payload.pallets_count or 1,
        total_boxes=tot_boxes,
        total_units=tot_units,
        status="PENDING_APPROVAL",
        packing_list_filename=payload.packing_list_filename,
        packing_list_data=payload.packing_list_data,
        commercial_invoice_filename=payload.commercial_invoice_filename,
        commercial_invoice_data=payload.commercial_invoice_data,
        ai_extracted_raw=payload.ai_extracted_raw,
        notes=payload.notes,
        created_by=payload.created_by or "Warehouse Manager",
        created_at=datetime.utcnow()
    )
    db.add(shipment)
    db.flush()

    for it in payload.items:
        style_clean = it.style.strip().upper()
        line_clean = it.line.strip() if it.line and it.line.strip() else None
        row_clean = it.row_pos.strip() if it.row_pos and it.row_pos.strip() else None
        sec_clean = it.section.strip() if it.section and it.section.strip() else None
        lvl_clean = it.level.strip() if it.level and it.level.strip() else None
        box_clean = it.box_num.strip() if it.box_num and it.box_num.strip() else None

        loc_meta = build_location_info(
            style=style_clean,
            line=line_clean,
            section=sec_clean,
            level=lvl_clean,
            row_pos=row_clean,
            box_num=box_clean
        )

        item_row = InboundShipmentItem(
            shipment_id=shipment.id,
            style=style_clean,
            brand=it.brand or loc_meta["brand"],
            warehouse_part=loc_meta["warehouse_part"],
            color=(it.color or "STANDARD").strip().upper(),
            size=(it.size or "OS").strip().upper(),
            line=loc_meta["line"],
            row_pos=loc_meta["row_pos"],
            section=loc_meta["section"],
            level=loc_meta["level"],
            box_num=loc_meta["box_num"],
            box_count=it.box_count or 1,
            pcs_per_box=it.pcs_per_box,
            quantity=it.quantity or 0,
            expected_quantity=it.expected_quantity,
            location=it.location or loc_meta["location"],
            notes=it.notes
        )
        db.add(item_row)

    db.commit()
    db.refresh(shipment)
    return shipment


@app.get("/api/inbound/shipments", dependencies=LOGIN_REQUIRED)
def list_inbound_shipments(
    status_filter: Optional[str] = Query(None, description="PENDING_APPROVAL | APPROVED | REJECTED"),
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List inbound shipments with summary counts.
    Used for Admin notification badge & history review.
    """
    q = db.query(InboundShipment)
    if status_filter:
        q = q.filter(InboundShipment.status == status_filter.upper())

    shipments = q.order_by(InboundShipment.created_at.desc()).limit(limit).all()

    pending_count = db.query(func.count(InboundShipment.id)).filter(
        InboundShipment.status == "PENDING_APPROVAL"
    ).scalar() or 0

    approved_count = db.query(func.count(InboundShipment.id)).filter(
        InboundShipment.status == "APPROVED"
    ).scalar() or 0

    return {
        "pending_count": pending_count,
        "approved_count": approved_count,
        "total_count": len(shipments),
        "shipments": [
            {
                "id": s.id,
                "shipment_number": s.shipment_number,
                "po_number": s.po_number,
                "carrier_vendor": s.carrier_vendor,
                "pallets_count": s.pallets_count,
                "total_boxes": s.total_boxes,
                "total_units": s.total_units,
                "status": s.status,
                "created_by": s.created_by,
                "approved_by": s.approved_by,
                "approved_at": s.approved_at.isoformat() if s.approved_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "items_count": len(s.items),
                "has_packing_list": bool(s.packing_list_data or s.packing_list_filename),
                "has_commercial_invoice": bool(s.commercial_invoice_data or s.commercial_invoice_filename)
            }
            for s in shipments
        ]
    }


@app.get("/api/inbound/shipments/{shipment_id}", response_model=InboundShipmentResponse, dependencies=LOGIN_REQUIRED)
def get_inbound_shipment_detail(shipment_id: int, db: Session = Depends(get_db)):
    """Retrieve full shipment details, line items, and document scan preview."""
    shipment = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Inbound shipment not found.")
    return shipment


@app.post("/api/inbound/shipments/{shipment_id}/approve", dependencies=ADMIN_ONLY)
def approve_inbound_shipment(
    shipment_id: int,
    payload: InboundApprovePayload,
    db: Session = Depends(get_db)
):
    """
    ADMIN CONFIRMATION:
    When Admin clicks Confirm, all verified line items in the shipment
    are automatically committed to PostgreSQL inventory and recorded in the audit trail.
    """
    from datetime import datetime

    shipment = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).with_for_update().first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Inbound shipment not found.")
    if shipment.status == "APPROVED":
        raise HTTPException(status_code=400, detail="Shipment has already been approved.")

    admin_name = (payload.approved_by or "Nandu (Admin)").strip()
    reason_note = f"Approved Inbound Shipment {shipment.shipment_number} (PO: {shipment.po_number or 'N/A'}, Pallets: {shipment.pallets_count})"
    if payload.notes:
        reason_note += f" - {payload.notes.strip()}"

    created_records = 0
    merged_records = 0
    total_units_committed = 0

    for it in shipment.items:
        if it.quantity <= 0:
            continue

        loc_meta = build_location_info(
            style=it.style,
            line=it.line,
            section=it.section,
            level=it.level,
            row_pos=it.row_pos,
            box_num=it.box_num
        )

        q = db.query(InventoryItem).filter(
            ACTIVE_ITEM,
            func.upper(InventoryItem.style) == it.style.upper(),
            func.upper(func.coalesce(InventoryItem.color, "STANDARD")) == it.color.upper(),
            func.upper(func.coalesce(InventoryItem.size, "OS")) == it.size.upper(),
            func.coalesce(InventoryItem.line, "") == (loc_meta["line"] or ""),
            func.coalesce(InventoryItem.section, "") == (loc_meta["section"] or ""),
            func.coalesce(InventoryItem.level, "") == (loc_meta["level"] or ""),
            func.coalesce(InventoryItem.row_pos, "") == (loc_meta["row_pos"] or ""),
        )
        if loc_meta["box_num"]:
            target = q.filter(func.coalesce(InventoryItem.box_num, "") == loc_meta["box_num"]).first()
        else:
            target = q.first()

        if target:
            target.quantity += it.quantity
            if it.pcs_per_box:
                target.pcs_per_box = it.pcs_per_box
            merged_records += 1
            total_units_committed += it.quantity

            db.add(StockMovement(
                item_id=target.id,
                style=target.style,
                change_amount=it.quantity,
                quantity_after=target.quantity,
                movement_type="INBOUND_SHIPMENT_APPROVED",
                reason=reason_note,
                staff_name=admin_name
            ))
        else:
            new_item = InventoryItem(
                style=it.style.upper(),
                brand=it.brand or loc_meta["brand"],
                warehouse_part=loc_meta["warehouse_part"],
                placement_type=loc_meta["placement_type"],
                location_code=loc_meta["location_code"],
                location=it.location or loc_meta["location"],
                color=it.color.upper(),
                size=it.size.upper(),
                line=loc_meta["line"],
                section=loc_meta["section"],
                level=loc_meta["level"],
                row_pos=loc_meta["row_pos"],
                box_num=loc_meta["box_num"],
                pcs_per_box=it.pcs_per_box,
                quantity=it.quantity
            )
            db.add(new_item)
            db.flush()
            created_records += 1
            total_units_committed += it.quantity

            db.add(StockMovement(
                item_id=new_item.id,
                style=new_item.style,
                change_amount=it.quantity,
                quantity_after=new_item.quantity,
                movement_type="INBOUND_SHIPMENT_APPROVED",
                reason=reason_note,
                staff_name=admin_name
            ))

    shipment.status = "APPROVED"
    shipment.approved_by = admin_name
    shipment.approved_at = datetime.utcnow()
    if payload.notes:
        shipment.notes = f"{shipment.notes or ''}\n[Admin Notes]: {payload.notes.strip()}".strip()

    db.commit()

    return {
        "status": "success",
        "message": f"Successfully approved {shipment.shipment_number}! {total_units_committed:,} pieces committed to PostgreSQL across {len(shipment.items)} items ({merged_records} merged, {created_records} new locations).",
        "shipment_id": shipment.id,
        "total_units_committed": total_units_committed,
        "merged_records": merged_records,
        "created_records": created_records
    }


@app.post("/api/inbound/shipments/{shipment_id}/reject", dependencies=ADMIN_ONLY)
def reject_inbound_shipment(
    shipment_id: int,
    payload: InboundRejectPayload,
    db: Session = Depends(get_db)
):
    """Admin rejects shipment with revision instructions."""

    shipment = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Inbound shipment not found.")

    shipment.status = "REJECTED"
    admin_name = (payload.rejected_by or "Nandu (Admin)").strip()
    shipment.notes = f"{shipment.notes or ''}\n[Rejected by {admin_name}]: {payload.reason.strip()}".strip()
    db.commit()

    return {"status": "success", "message": f"Shipment {shipment.shipment_number} rejected: {payload.reason}"}


@app.delete("/api/inbound/shipments/{shipment_id}", dependencies=ADMIN_ONLY)
def delete_inbound_shipment(shipment_id: int, db: Session = Depends(get_db)):
    """Delete draft or rejected shipment."""
    shipment = db.query(InboundShipment).filter(InboundShipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Inbound shipment not found.")
    if shipment.status == "APPROVED":
        raise HTTPException(status_code=400, detail="Cannot delete an approved shipment.")

    db.delete(shipment)
    db.commit()
    return {"status": "success", "message": f"Shipment {shipment.shipment_number} deleted."}


# ======================================================================================
# INTERNAL SERVICE API (service-to-service only)
# Used by other microservices (e.g. picking-service). Protected by a shared secret in the
# X-Internal-Key header. Disabled entirely if INTERNAL_API_KEY is not configured.
# ======================================================================================

# No default: if INTERNAL_API_KEY is unset, every /api/internal/* call is refused (503).
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()
if not INTERNAL_API_KEY:
    print("[Internal API] WARNING: INTERNAL_API_KEY is not set — QR picking and vision lookups are disabled.", flush=True)


def require_internal_service(request: Request):
    if not INTERNAL_API_KEY:
        raise HTTPException(status_code=503, detail="Internal service API is not configured (INTERNAL_API_KEY missing).")
    supplied = request.headers.get("X-Internal-Key", "")
    if not _hmac.compare_digest(supplied, INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid internal service key.")
    return True


def _norm_line(v): return _norm_coord(v, ("LINE ", "LINE#", "LINE-", "LN ", "L-", "L"))
def _norm_section(v): return _norm_coord(v, ("SECTION ", "SECTION#", "SEC ", "SEC#", "SEC-", "S-"))
def _norm_level(v): return _norm_coord(v, ("LEVEL ", "LEVEL#", "LVL ", "LVL#", "LVL-", "LV-", "LV"))


class InternalPickPayload(BaseModel):
    style: str
    warehouse_part: str = "PART_1"
    line: str
    section: str
    level: str
    quantity: int = 1
    item_id: Optional[int] = None      # required when style has several sizes/colors at this level
    staff_name: str
    source: Optional[str] = "QR_PICK"


@app.get("/api/internal/locations/stock")
def internal_location_stock(
    warehouse_part: str = Query("PART_1"),
    line: str = Query(...),
    section: str = Query(...),
    db: Session = Depends(get_db),
    _: bool = Depends(require_internal_service),
):
    """All inventory rows in one Line/Section (every level). Used by picking-service to build its UI."""
    ln, sec = _norm_line(line), _norm_section(section)
    rows = db.query(InventoryItem).filter(
        ACTIVE_ITEM,
        InventoryItem.warehouse_part == warehouse_part,
        InventoryItem.line == ln,
        InventoryItem.section == sec,
    ).order_by(InventoryItem.level.asc(), InventoryItem.style.asc(), InventoryItem.size.asc()).all()
    return {
        "warehouse_part": warehouse_part,
        "line": ln,
        "section": sec,
        "items": [
            {
                "item_id": r.id,
                "style": r.style,
                "brand": r.brand,
                "color": r.color,
                "size": r.size,
                "level": r.level,
                "quantity": r.quantity,
                "location": r.location,
            }
            for r in rows
        ],
    }


@app.post("/api/internal/inventory/pick")
def internal_pick(
    payload: InternalPickPayload,
    db: Session = Depends(get_db),
    _: bool = Depends(require_internal_service),
):
    """Atomically deduct picked pieces from one exact shelf position and write an audit movement."""
    if payload.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1.")
    style = (payload.style or "").strip()
    if not style:
        raise HTTPException(status_code=400, detail="Style is required.")
    ln, sec, lvl = _norm_line(payload.line), _norm_section(payload.section), _norm_level(payload.level)

    q = db.query(InventoryItem).filter(
        ACTIVE_ITEM,
        InventoryItem.warehouse_part == payload.warehouse_part,
        InventoryItem.line == ln,
        InventoryItem.section == sec,
        InventoryItem.level == lvl,
        func.upper(InventoryItem.style) == style.upper(),
    )
    if payload.item_id is not None:
        q = q.filter(InventoryItem.id == payload.item_id)
    matches = q.with_for_update().all()

    where = f"Line {ln} • Sec {sec} • Lvl {lvl}"
    if not matches:
        raise HTTPException(status_code=404, detail=f"Style '{style.upper()}' is not stocked at {where}.")
    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Style '{style.upper()}' has {len(matches)} sizes/colors at {where}. Choose one.",
                "options": [
                    {"item_id": m.id, "size": m.size, "color": m.color, "quantity": m.quantity}
                    for m in matches
                ],
            },
        )

    item = matches[0]
    if payload.quantity > item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {item.quantity} pcs of {item.style} (size {item.size}) at {where}. Cannot take {payload.quantity}.",
        )

    item.quantity -= payload.quantity
    db.add(StockMovement(
        item_id=item.id,
        style=item.style,
        change_amount=-payload.quantity,
        quantity_after=item.quantity,
        movement_type=(payload.source or "QR_PICK")[:50],
        reason=f"QR pick @ {where}",
        staff_name=(payload.staff_name or "Unknown")[:100],
    ))
    db.commit()
    db.refresh(item)
    return {
        "status": "ok",
        "item_id": item.id,
        "style": item.style,
        "size": item.size,
        "color": item.color,
        "level": item.level,
        "location": item.location,
        "picked": payload.quantity,
        "quantity_after": item.quantity,
    }


@app.get("/api/internal/catalog")
def internal_catalog(
    db: Session = Depends(get_db),
    _: bool = Depends(require_internal_service),
):
    """Export live inventory styles, colors, sizes, and pcs_per_box for training vision-llm-service."""
    from collections import Counter
    rows = db.query(
        InventoryItem.style,
        InventoryItem.brand,
        InventoryItem.color,
        InventoryItem.size,
        InventoryItem.pcs_per_box,
        InventoryItem.quantity,
    ).filter(ACTIVE_ITEM).all()

    styles_map: dict = {}
    colors_cnt: Counter = Counter()
    sizes_cnt: Counter = Counter()
    pcs_cnt: Counter = Counter()
    qty_cnt: Counter = Counter()

    for style, brand, color, size, pcs_per_box, qty in rows:
        st = (style or "").strip().upper()
        if not st:
            continue
        rec = styles_map.setdefault(st, {
            "style": st,
            "brand": (brand or "ALLBIRDS").upper(),
            "colors": set(),
            "sizes": set(),
            "pcs_per_box": set(),
        })
        col = (color or "").strip().upper()
        if col and col != "STANDARD":
            rec["colors"].add(col)
            colors_cnt[col] += 1
        sz = (size or "").strip().upper()
        if sz:
            rec["sizes"].add(sz)
            sizes_cnt[sz] += 1
        if pcs_per_box and pcs_per_box > 0:
            rec["pcs_per_box"].add(int(pcs_per_box))
            pcs_cnt[int(pcs_per_box)] += 1
        if qty and qty > 0:
            qty_cnt[int(qty)] += 1

    return {
        "styles": [
            {
                "style": v["style"],
                "brand": v["brand"],
                "colors": sorted(v["colors"]),
                "sizes": sorted(v["sizes"]),
                "pcs_per_box": sorted(v["pcs_per_box"]),
            }
            for v in sorted(styles_map.values(), key=lambda x: x["style"])
        ],
        "colors": [k for k, _ in colors_cnt.most_common()],
        "sizes": [k for k, _ in sizes_cnt.most_common()],
        "common_pcs_per_box": [k for k, _ in pcs_cnt.most_common(30)],
        "common_quantities": [k for k, _ in qty_cnt.most_common(40)],
    }


@app.get("/api/internal/styles/lookup")
def internal_style_lookup(
    style: str = Query(...),
    color: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_internal_service),
):
    """Return live rack locations and quantities for a scanned style (used by vision-llm-service)."""
    q = db.query(InventoryItem).filter(ACTIVE_ITEM, func.upper(InventoryItem.style) == style.strip().upper())
    items = q.order_by(InventoryItem.quantity.desc(), InventoryItem.location.asc()).limit(40).all()
    if color:
        cu = color.strip().upper()
        colored = [i for i in items if (i.color or "").upper() == cu]
        if colored:
            items = colored
    return {
        "style": style.strip().upper(),
        "items": [
            {
                "id": i.id,
                "style": i.style,
                "brand": i.brand,
                "color": i.color,
                "size": i.size,
                "quantity": i.quantity,
                "location": i.location,
            }
            for i in items
        ],
    }


# ======================================================================================
# API GATEWAY: forward /pick/* -> picking-service and /scan/* -> vision-llm-service.
# ======================================================================================

PICKING_SERVICE_URL = os.getenv("PICKING_SERVICE_URL", "http://localhost:8001").rstrip("/")
VISION_SERVICE_URL = os.getenv("VISION_SERVICE_URL", "http://localhost:8002").rstrip("/")
_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
                "trailers", "transfer-encoding", "upgrade", "host", "content-length", "content-encoding"}
# Never forward a client-supplied service key; the gateway adds it itself when allowed.
_STRIP_FROM_CLIENT = {"x-internal-key"}

# Vision endpoints that change the model: gateway adds X-Internal-Key only for logged-in Admin/Manager.
_VISION_PROTECTED_PATHS = {"api/train", "api/feedback"}


async def _proxy_to_service(request: Request, target_url: str, fallback_url: str, service_label: str,
                            extra_headers: Optional[dict] = None):
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in _HOP_HEADERS and k.lower() not in _STRIP_FROM_CLIENT}
    if extra_headers:
        headers.update(extra_headers)
    headers["X-Forwarded-Host"] = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    headers["X-Forwarded-Proto"] = request.headers.get("x-forwarded-proto") or request.url.scheme
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                upstream = await client.request(
                    request.method, target_url, params=request.query_params,
                    headers=headers, content=body,
                )
            except httpx.RequestError:
                if target_url == fallback_url:
                    raise
                upstream = await client.request(
                    request.method, fallback_url, params=request.query_params,
                    headers=headers, content=body,
                )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail=f"{service_label} is unavailable. Please try again shortly.")
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_HEADERS}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)


@app.api_route("/pick", methods=["GET", "POST"], include_in_schema=False)
@app.api_route("/pick/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def gateway_picking_service(request: Request, path: str = ""):
    url = f"{PICKING_SERVICE_URL}/pick/{path}" if path else f"{PICKING_SERVICE_URL}/pick"
    fallback_url = f"http://127.0.0.1:8001/pick/{path}" if path else "http://127.0.0.1:8001/pick"
    return await _proxy_to_service(request, url, fallback_url, "Picking service")


@app.api_route("/scan", methods=["GET", "POST"], include_in_schema=False)
@app.api_route("/scan/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def gateway_vision_service(request: Request, path: str = ""):
    url = f"{VISION_SERVICE_URL}/scan/{path}" if path else f"{VISION_SERVICE_URL}/scan"
    fallback_url = f"http://127.0.0.1:8002/scan/{path}" if path else "http://127.0.0.1:8002/scan"
    extra = None
    if path.strip("/") in _VISION_PROTECTED_PATHS:
        db = SessionLocal()
        try:
            user = get_optional_user(request, db)
        finally:
            db.close()
        if not user or (user.role or "").upper() not in ("ADMIN", "MANAGER"):
            raise HTTPException(status_code=403, detail="Admin or Manager login required to train the model.")
        if not INTERNAL_API_KEY:
            raise HTTPException(status_code=503, detail="Model training is disabled: INTERNAL_API_KEY is not set.")
        extra = {"X-Internal-Key": INTERNAL_API_KEY}
    return await _proxy_to_service(request, url, fallback_url, "Vision SLM service", extra_headers=extra)


def _safe_next(next_url: Optional[str]) -> Optional[str]:
    """Only allow same-site relative redirects after login (prevents open redirects)."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return None


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        ico_file = os.path.join(static_dir, "favicon.ico")
        if os.path.exists(ico_file):
            return FileResponse(ico_file, media_type="image/x-icon")
        return FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")


    @app.get("/login")
    def serve_login_page(request: Request, db: Session = Depends(get_db)):
        user = get_optional_user(request, db)
        if user:
            return RedirectResponse(url=_safe_next(request.query_params.get("next")) or "/", status_code=302)
        return FileResponse(os.path.join(static_dir, "login.html"))

    @app.get("/")
    def serve_frontend(request: Request, db: Session = Depends(get_db)):
        user = get_optional_user(request, db)
        if not user:
            return RedirectResponse(url="/login", status_code=302)
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/manage")
    def serve_manage_page(request: Request, db: Session = Depends(get_db)):
        user = get_optional_user(request, db)
        if not user:
            return RedirectResponse(url="/login", status_code=302)
        if user.role != "ADMIN" and user.role != "MANAGER":
            # Manager & Floor Staff only get the Single-View Lookup & Print Pick Sheet dashboard
            return RedirectResponse(url="/", status_code=302)
        return FileResponse(os.path.join(static_dir, "manage.html"))
