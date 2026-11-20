"""Phase 1b: rows with history are deactivated (hidden, history kept), never deleted."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import InventoryItem, StockMovement

INTERNAL = {"X-Internal-Key": "test-internal-key-0123456789"}


def _item(db, style="A1", qty=0, history=True):
    item = InventoryItem(style=style, location="Line 1 • Sec 1 • Lvl 1", warehouse_part="PART_1",
                         line="1", section="1", level="1", quantity=qty)
    db.add(item)
    db.flush()
    if history:
        db.add(StockMovement(item_id=item.id, style=style, change_amount=5, quantity_after=qty,
                             movement_type="TEST", staff_name="t"))
    db.commit()
    return item


def test_database_refuses_to_delete_item_with_history(db):
    item = _item(db)
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM inventory_items WHERE id = :i"), {"i": item.id})
        db.commit()
    db.rollback()
    assert db.query(StockMovement).filter_by(item_id=item.id).count() == 1


def test_orm_delete_does_not_cascade_history(db):
    item = _item(db)
    db.delete(item)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(StockMovement).count() == 1


def test_new_rows_are_active(db):
    assert _item(db, history=False).is_active is True


def test_staff_cannot_deactivate(staff, db):
    item = _item(db)
    assert staff.post(f"/api/items/{item.id}/deactivate").status_code == 403


def test_deactivate_requires_zero_quantity(manager, db):
    item = _item(db, qty=4)
    r = manager.post(f"/api/items/{item.id}/deactivate")
    assert r.status_code == 409
    assert "4 pcs" in r.json()["detail"]
    db.expire_all()
    assert db.get(InventoryItem, item.id).is_active is True


def test_delete_409_points_to_deactivate(manager, db):
    item = _item(db)
    r = manager.delete(f"/api/items/{item.id}")
    assert r.status_code == 409
    assert "Deactivate" in r.json()["detail"]


def test_deactivate_hides_row_everywhere_and_keeps_history(manager, anon, db):
    item = _item(db, style="ZZ1")
    keep = _item(db, style="ZZ2", qty=3, history=False)

    r = manager.post(f"/api/items/{item.id}/deactivate")
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    mv = db.query(StockMovement).filter_by(item_id=item.id).order_by(StockMovement.id.desc()).first()
    assert mv.movement_type == "DEACTIVATE" and mv.change_amount == 0
    assert mv.staff_name == "Mgrtest Person"  # the logged-in user
    assert db.query(StockMovement).filter_by(item_id=item.id).count() == 2

    assert manager.get("/api/stats").json()["total_records"] == 1
    assert manager.get("/api/styles/ZZ1").status_code == 404
    batch = manager.get("/api/styles-batch", params={"styles": "ZZ1,ZZ2"}).json()
    assert [i["id"] for i in batch["items"]] == [keep.id]
    assert [s["style"] for s in manager.get("/api/styles").json()] == ["ZZ2"]
    assert [i["id"] for i in manager.get("/api/location-search", params={"style": "ZZ"}).json()] == [keep.id]
    both = manager.get("/api/location-search", params={"style": "ZZ", "include_inactive": "true"}).json()
    assert {i["id"] for i in both} == {item.id, keep.id}
    assert "ZZ1" not in manager.get("/api/export-csv").text

    stock = anon.get("/api/internal/locations/stock", params={"line": "1", "section": "1"}, headers=INTERNAL)
    assert stock.status_code == 200
    assert [i["item_id"] for i in stock.json()["items"]] == [keep.id]
    look = anon.get("/api/internal/styles/lookup", params={"style": "ZZ1"}, headers=INTERNAL)
    assert look.status_code == 200 and look.json()["items"] == []

    # history is still visible in the movement log
    assert any(m["movement_type"] == "DEACTIVATE" for m in manager.get("/api/movements").json())


def test_deactivated_row_cannot_be_adjusted_until_reactivated(manager, db):
    item = _item(db)
    assert manager.post(f"/api/items/{item.id}/deactivate").status_code == 200
    assert manager.post(f"/api/items/{item.id}/adjust", json={"change_amount": 1}).status_code == 409
    assert manager.post(f"/api/items/{item.id}/set-quantity", json={"new_quantity": 2}).status_code == 409

    r = manager.post(f"/api/items/{item.id}/reactivate")
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert manager.post(f"/api/items/{item.id}/adjust", json={"change_amount": 1}).status_code == 200
    types = [m.movement_type for m in db.query(StockMovement).filter_by(item_id=item.id).order_by(StockMovement.id)]
    assert types == ["TEST", "DEACTIVATE", "REACTIVATE", "QUICK_ADJUST"]


def test_sheet_in_does_not_merge_into_deactivated_row(manager, db):
    item = _item(db, style="ZZ9")
    manager.post(f"/api/items/{item.id}/deactivate")
    r = manager.post("/api/sheet-submit", json={"rows": [
        {"action": "IN", "style": "ZZ9", "line": "1", "section": "1", "level": "1", "quantity": 2}]})
    assert r.status_code == 200, r.text
    assert r.json()["inserted_count"] == 1
    db.expire_all()
    assert db.get(InventoryItem, item.id).quantity == 0
    assert db.get(InventoryItem, item.id).is_active is False
