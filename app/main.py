import os
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, distinct

from app.database import get_db, init_db, SessionLocal
from app.models import InventoryItem, StockMovement
from app.schemas import (
    ItemCreate, ItemUpdatePayload, ItemResponse, StyleSummary,
    StockAdjustPayload, SetQuantityPayload, WarehouseStats,
    SheetRowItem, SheetSubmitPayload, BulkDeletePayload, StyleRenamePayload
)

def seed_if_empty():
    """Create tables and auto-seed from CSV if the database is empty (e.g. fresh Railway Postgres)."""
    try:
        init_db()
        db = SessionLocal()
        try:
            count = db.query(InventoryItem).count()
        finally:
            db.close()
        if count == 0:
            print("[Database] Empty database detected. Auto-seeding records from CSV...", flush=True)
            from scripts.migrate_inventory import migrate
            migrate()
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
        match_clauses.append(func.upper(InventoryItem.style).like(f"{tok}%"))

    items = db.query(InventoryItem).filter(
        or_(*match_clauses)
    ).order_by(
        InventoryItem.line.asc(),
        InventoryItem.section.asc(),
        InventoryItem.level.asc(),
        InventoryItem.style.asc()
    ).all()

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
    new_item = InventoryItem(**payload.model_dump())
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


def _build_location(line, section, level, row_pos, box_num) -> str:
    parts = []
    if line: parts.append(f"Line {line}")
    if section: parts.append(f"Sec {section}")
    if level: parts.append(f"Lvl {level}")
    if row_pos: parts.append(f"Row {row_pos}")
    if box_num: parts.append(f"Box {box_num}")
    return " • ".join(parts) if parts else "Unassigned"


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
            line = _clean_str(raw.line)
            section = _clean_str(raw.section)
            level = _clean_str(raw.level)
            row_pos = _clean_str(raw.row_pos)
            box_num = _clean_str(raw.box_num)
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

            loc_str = _build_location(line, section, level, row_pos, box_num)

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
                exact_match.location = loc_str
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
                new_item = InventoryItem(
                    style=style,
                    color=color,
                    size=size,
                    line=line,
                    section=section,
                    level=level,
                    row_pos=row_pos,
                    box_num=box_num,
                    location=loc_str,
                    pcs_per_box=pcs_per_box,
                    quantity=qty,
                )
                db.add(new_item)
                db.flush()
                inserted_count += 1
                total_pieces_in += qty
                db.add(StockMovement(
                    item_id=new_item.id,
                    style=new_item.style,
                    change_amount=qty,
                    quantity_after=new_item.quantity,
                    movement_type="NEW_LOCATION_IN",
                    reason=f"{note} (New location entry)",
                    staff_name=staff,
                ))

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
    if line and line.strip():
        q = q.filter(func.upper(func.coalesce(InventoryItem.line, "")) == line.strip().upper())
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
    item.location = _build_location(item.line, item.section, item.level, item.row_pos, item.box_num)

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

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/manage")
    def serve_manage_page():
        return FileResponse(os.path.join(static_dir, "manage.html"))
