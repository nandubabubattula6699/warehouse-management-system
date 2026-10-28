import os
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, distinct

from app.database import get_db, init_db
from app.models import InventoryItem, StockMovement
from app.schemas import (
    ItemCreate, ItemResponse, StyleSummary,
    StockAdjustPayload, SetQuantityPayload, WarehouseStats
)

app = FastAPI(
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

@app.on_event("startup")
def on_startup():
    try:
        init_db()
        # Auto-seed if database is empty (e.g. freshly deployed on Railway)
        db = SessionLocal()
        count = db.query(InventoryItem).count()
        if count == 0:
            print("[Database] Empty database detected. Auto-seeding 9,171 records from CSV...")
            from scripts.migrate_inventory import migrate
            migrate()
        db.close()
    except Exception as e:
        print(f"[Database Startup Warning]: {e}")

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
    limit: int = Query(100, ge=1, le=1000),
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
    # Split by comma or whitespace
    import re
    raw_list = [s.strip().upper() for s in re.split(r"[,\s]+", styles) if s.strip()]
    if not raw_list:
        raise HTTPException(status_code=400, detail="No styles provided")

    items = db.query(InventoryItem).filter(
        func.upper(InventoryItem.style).in_(raw_list)
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
        "items": [ItemResponse.from_orm(i) for i in items]
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
        "items": [ItemResponse.from_orm(i) for i in items]
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
    new_item = InventoryItem(**payload.dict())
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

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(static_dir, "index.html"))
