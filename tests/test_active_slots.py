"""Migration 0003: one ACTIVE row per style + color + size + location (incl. box #); admin audit export."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryItem, StockMovement


def _row(db, style="A1", qty=5, active=True, box=None, color="STANDARD", size="9"):
    item = InventoryItem(style=style, color=color, size=size, line="2", section="1", level="4", box_num=box,
                         location="Line 2 • Sec 1 • Lvl 4", warehouse_part="PART_1", quantity=qty, is_active=active)
    db.add(item)
    db.commit()
    return item


def test_db_rejects_second_active_row_in_slot(db):
    _row(db)
    with pytest.raises(IntegrityError):
        _row(db, style="a1", color="standard")  # same slot, different case
    db.rollback()


def test_inactive_rows_and_other_boxes_or_sizes_are_allowed(db):
    _row(db)
    _row(db, active=False)
    _row(db, active=False)
    _row(db, box="3")
    _row(db, size="10")
    assert db.query(InventoryItem).count() == 5


def test_api_create_into_occupied_slot_is_409(manager, db):
    _row(db, style="A1")
    r = manager.post("/api/items", json={"style": "A1", "color": "STANDARD", "size": "9", "line": "2",
                                         "section": "1", "level": "4", "quantity": 3, "location": "x"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]
    assert db.query(InventoryItem).count() == 1


def test_reactivate_into_occupied_slot_is_409(manager, db):
    old = _row(db, qty=0, active=False)
    _row(db, qty=4)
    r = manager.post(f"/api/items/{old.id}/reactivate")
    assert r.status_code == 409
    db.expire_all()
    assert db.get(InventoryItem, old.id).is_active is False
    assert db.query(StockMovement).filter_by(item_id=old.id).count() == 0  # nothing half-saved


def test_sheet_rows_for_same_new_slot_merge_into_one_row(manager, db):
    r = manager.post("/api/sheet-submit", json={"rows": [
        {"action": "IN", "style": "NEW1", "size": "9", "line": "2", "section": "1", "level": "4", "quantity": 20},
        {"action": "IN", "style": "NEW1", "size": "9", "line": "2", "section": "1", "level": "4", "quantity": 20},
    ]})
    assert r.status_code == 200, r.text
    rows = db.query(InventoryItem).filter_by(style="NEW1").all()
    assert len(rows) == 1 and rows[0].quantity == 40


def test_export_default_excludes_deactivated(manager, db):
    _row(db, style="LIVE1")
    _row(db, style="GONE1", qty=0, active=False)
    csv_text = manager.get("/api/export-csv").text
    assert "LIVE1" in csv_text and "GONE1" not in csv_text
    assert "ACTIVE" not in csv_text.splitlines()[0]


def test_export_include_deactivated_is_admin_only(manager, admin, db):
    _row(db, style="LIVE1")
    _row(db, style="GONE1", qty=0, active=False)
    assert manager.get("/api/export-csv", params={"include_inactive": "true"}).status_code == 403
    r = admin.get("/api/export-csv", params={"include_inactive": "true"})
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert lines[0].endswith(",ACTIVE")
    assert any(ln.startswith("GONE1,") and ln.endswith(",NO") for ln in lines)
    assert any(ln.startswith("LIVE1,") and ln.endswith(",YES") for ln in lines)
    assert "incl_deactivated" in r.headers["content-disposition"]


def test_staff_cannot_export(staff):
    assert staff.get("/api/export-csv").status_code == 403
