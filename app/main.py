import os
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import Request, Response
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, distinct

from app.database import get_db, init_db, SessionLocal
from app.models import WarehouseLocation, InventoryItem, StockMovement, WarehouseUser
from app.auth import (
    SESSION_COOKIE_NAME, hash_password, verify_password,
    ensure_default_admin, get_optional_user, require_user, require_admin
)
from app.location_engine import build_location_info, ensure_schema_and_locations_seeded
from app.schemas import (
    ItemCreate, ItemUpdatePayload, ItemResponse, StyleSummary,
    StockAdjustPayload, SetQuantityPayload, WarehouseStats,
    SheetRowItem, SheetSubmitPayload, BulkDeletePayload, StyleRenamePayload,
    ReceivingPayload
)

def seed_if_empty():
    """Create tables, upgrade 2-Part Warehouse schema/locations, and auto-seed from CSV if empty."""
    try:
        init_db()
        db_map = SessionLocal()
        try:
            ensure_schema_and_locations_seeded(db_map)
            ensure_default_admin(db_map)
        finally:
            db_map.close()

        db = SessionLocal()
        try:
            count = db.query(func.count(InventoryItem.id)).scalar() or 0
        finally:
            db.close()
        if count == 0:
            print("[Database] Empty database detected. Auto-seeding records from CSV...", flush=True)
            from scripts.migrate_inventory import migrate
            migrate()
            db_map2 = SessionLocal()
            try:
                ensure_schema_and_locations_seeded(db_map2)
            finally:
                db_map2.close()
        else:
            print(f"[Database] {count:,} inventory records present.", flush=True)
    except Exception as e:
        print(f"[Database Startup Warning]: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Warehouse Inventory OS - Manager Multi-Style View",
    description="Multi-style tracking, location mapping, and live stock adjustments in PostgreSQL.",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "PostgreSQL"}

@app.get("/api/stats", response_model=WarehouseStats)
def get_stats(db: Session = Depends(get_db)):
    total_styles = db.query(func.count(distinct(InventoryItem.style))).scalar() or 0
    total_records = db.query(func.count(InventoryItem.id)).scalar() or 0
    total_units = db.query(func.sum(InventoryItem.quantity)).scalar() or 0
    total_locations = db.query(func.count(distinct(InventoryItem.location))).scalar() or 0

    return WarehouseStats(
        total_styles=total_styles,
        total_records=total_records,
        total_units=int(total_units),
        total_locations=total_locations
    )

@app.get("/api/styles")
def list_styles(
    q: Optional[str] = Query(None, description="Search style code e.g. A12"),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db)
):
    query = db.query(
        InventoryItem.style,
        func.sum(InventoryItem.quantity).label("total_qty"),
        func.count(InventoryItem.id).label("location_count")
    )
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
@app.get("/api/styles-batch")
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
        or_(*match_clauses)
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

@app.get("/api/styles/{style_code}")
def get_style_detail(style_code: str, db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(
        InventoryItem.style.ilike(style_code.strip())
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

@app.post("/api/items/{item_id}/adjust", response_model=ItemResponse)
def adjust_quantity(
    item_id: int,
    payload: StockAdjustPayload,
    db: Session = Depends(get_db)
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

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
        staff_name=payload.staff_name or "Manager"
    )
    db.add(m)
    db.commit()
    db.refresh(item)
    return item

@app.post("/api/items/{item_id}/set-quantity", response_model=ItemResponse)
def set_quantity(
    item_id: int,
    payload: SetQuantityPayload,
    db: Session = Depends(get_db)
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

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
        staff_name=payload.staff_name or "Manager"
    )
    db.add(m)
    db.commit()
    db.refresh(item)
    return item

@app.post("/api/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
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

@app.delete("/api/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"message": f"Item {item.style} at location {item.location} deleted."}

@app.get("/api/movements")
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


@app.post("/api/sheet-submit")
def submit_manager_sheet(payload: SheetSubmitPayload, db: Session = Depends(get_db)):
    """
    Process a Manager Sheet (10-25 rows or 1,000+ rows from CSV):
    Supports per-row actions:
      - IN: Add pieces to existing location or create new style/location
      - OUT: Deduct pieces from matching location
      - SET: Set exact pieces at location (or create if new)
      - DELETE: Delete matching location record
    """
    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided in sheet.")

    # Pre-check which styles already exist in DB before this sheet
    all_existing_styles = {
        r[0].upper() for r in db.query(distinct(InventoryItem.style)).all() if r[0]
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
                db.delete(target)
                deleted_count += 1
                continue

            if action == "OUT":
                # Deduct stock from matching location (or across matching locations for that style/color/size)
                target = exact_match or q.order_by(InventoryItem.quantity.desc()).first()
                if not target:
                    # Fallback: if manager only gave style + color + size without exact row/box
                    fallback_q = db.query(InventoryItem).filter(
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
                inserted_count += 1
                total_pieces_in += qty

        db.commit()
    except HTTPException:
        db.rollback()
        raise
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


@app.get("/api/location-search")
def search_locations(
    style: Optional[str] = Query(None),
    line: Optional[str] = Query(None),
    row_pos: Optional[str] = Query(None),
    warehouse_part: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Search inventory records by style and/or warehouse location coordinates for editing or deleting."""
    q = db.query(InventoryItem)
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
def update_item_full(item_id: int, payload: ItemUpdatePayload, db: Session = Depends(get_db)):
    """Edit any field of an inventory row (style, color, size, line, section, level, row, box/cartons, quantity)."""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Location record not found.")
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
        staff_name=payload.staff_name or "Nandu",
    ))
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/items/bulk-delete")
def bulk_delete_items(payload: BulkDeletePayload, db: Session = Depends(get_db)):
    """Delete multiple selected location records at once."""
    if not payload.item_ids:
        raise HTTPException(status_code=400, detail="No item IDs selected.")
    deleted = db.query(InventoryItem).filter(InventoryItem.id.in_(payload.item_ids)).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok", "deleted_count": deleted}


@app.post("/api/styles/rename")
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
def export_inventory_csv(db: Session = Depends(get_db)):
    """Export all inventory rows as a CSV file."""
    import csv
    import io
    items = db.query(InventoryItem).order_by(InventoryItem.style.asc(), InventoryItem.line.asc(), InventoryItem.section.asc()).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["SKU", "COLOR", "ROW", "LINE", "SECTION", "LEVEL", "SIZE", "PCS/BOX", "QTY", "BOX #"])
    for i in items:
        writer.writerow([
            i.style, i.color or "", i.row_pos or "", i.line or "",
            i.section or "", i.level or "", i.size or "",
            i.pcs_per_box if i.pcs_per_box is not None else "",
            i.quantity, i.box_num or ""
        ])
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=warehouse_inventory_export.csv"}
    )


@app.get("/api/warehouse-overview")
def get_warehouse_overview(db: Session = Depends(get_db)):
    """
    Complete 50,000+ sq ft 2-Part Warehouse Map Overview:
      - PART_1: Allbirds Zone (14 Lines, each 32-35 Sections, 4 Levels)
      - PART_2: Von Dutch & Valentino Zone (14 Rows + WALL, 36 Sections + Ground FRONT/BACK + WALL, 4 Levels)
    """
    items = db.query(InventoryItem).all()

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


@app.get("/api/warehouse-map/aisle")
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
            func.coalesce(InventoryItem.line, "") == a
        ).order_by(InventoryItem.section.asc(), InventoryItem.level.asc(), InventoryItem.style.asc()).all()
    else:
        items = db.query(InventoryItem).filter(
            func.upper(func.coalesce(InventoryItem.row_pos, "")) == a
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
        "aisle_label": f"Line {a} (Allbirds)" if p == "PART_1" else (f"WALL Zone" if a == "WALL" else f"Row {a} (Von Dutch / Valentino)"),
        "total_sections_occupied": len(sorted_sections),
        "total_units": sum(s["total_units"] for s in sorted_sections),
        "total_records": sum(s["total_records"] for s in sorted_sections),
        "sections": sorted_sections,
    }



# ================= AUTHENTICATION & USER ACCESS CONTROL ENDPOINTS =================
class LoginPayload(BaseModel):
    username: str
    password: str


class SignupPayload(BaseModel):
    full_name: str
    username: str
    email: Optional[str] = None
    password: str
    role: Optional[str] = "STAFF"
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
    ensure_default_admin(db)
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
    ensure_default_admin(db)
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

    new_u = WarehouseUser(
        username=uname,
        email=email_clean,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=(payload.role or "STAFF").upper(),
        assigned_zone=(payload.assigned_zone or "ALL_ZONES").upper(),
        is_approved=0,  # Requires Admin (Nandu) approval
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


@app.post("/api/receiving")
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

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/login")
    def serve_login_page(request: Request, db: Session = Depends(get_db)):
        user = get_optional_user(request, db)
        if user:
            return RedirectResponse(url="/", status_code=302)
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
