"""Migration 0003: Part 2 (Rows) only - one ACTIVE row per location + style + color + size + pack size.
Part 1 (Allbirds, Lines) keeps one row per carton. Also: admin audit export."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryItem, StockMovement

# Release 1b-a ships without migration 0003 (the unique index); these tests come back with 1b-b.
needs_0003 = pytest.mark.skip(reason="1b-a: migration 0003 (Part 2 unique slot index) ships in 1b-b")


def _p2(db, style="VDBP-039", qty=8, active=True, box=None, color="CAMO", size="OS", pcs=8, row="4"):
    item = InventoryItem(style=style, color=color, size=size, row_pos=row, section="21", level="1", box_num=box,
                         location=f"Row {row} • Sec 21 • Lvl 1", warehouse_part="PART_2", brand="VON DUTCH",
                         pcs_per_box=pcs, quantity=qty, is_active=active)
    db.add(item)
    db.commit()
    return item


def _p1(db, style="TB1WJBK", qty=20, box=None):
    item = InventoryItem(style=style, color="STANDARD", size="7", line="2", section="1", level="4", box_num=box,
                         location="Line 2 • Sec 1 • Lvl 4", warehouse_part="PART_1", brand="ALLBIRDS",
                         pcs_per_box=20, quantity=qty)
    db.add(item)
    db.commit()
    return item


@needs_0003
def test_db_rejects_second_active_part2_row_in_slot(db):
    _p2(db)
    with pytest.raises(IntegrityError):
        _p2(db, style="vdbp-039", color="camo")  # same slot, different case
    db.rollback()


@needs_0003
def test_part2_box_number_is_not_part_of_the_slot(db):
    _p2(db)
    with pytest.raises(IntegrityError):
        _p2(db, box="5")
    db.rollback()


def test_part2_inactive_rows_and_other_pack_sizes_rows_or_sizes_are_allowed(db):
    _p2(db)
    _p2(db, active=False)
    _p2(db, active=False)
    _p2(db, pcs=12)
    _p2(db, size="L")
    _p2(db, row="5")
    assert db.query(InventoryItem).count() == 6


def test_part1_lines_keep_one_row_per_carton(db):
    for _ in range(19):
        _p1(db)
    assert db.query(InventoryItem).filter_by(style="TB1WJBK").count() == 19


@needs_0003
def test_api_create_into_occupied_part2_slot_is_409(manager, db):
    _p2(db)
    r = manager.post("/api/items", json={"style": "VDBP-039", "color": "CAMO", "size": "OS", "row_pos": "4",
                                         "section": "21", "level": "1", "pcs_per_box": 8, "quantity": 8,
                                         "location": "x"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]
    assert db.query(InventoryItem).count() == 1


def test_api_create_second_carton_row_on_a_line_is_allowed(manager, db):
    _p1(db)
    r = manager.post("/api/items", json={"style": "TB1WJBK", "color": "STANDARD", "size": "7", "line": "2",
                                         "section": "1", "level": "4", "pcs_per_box": 20, "quantity": 20,
                                         "location": "x"})
    assert r.status_code == 201, r.text
    assert db.query(InventoryItem).count() == 2


@needs_0003
def test_reactivate_into_occupied_part2_slot_is_409(manager, db):
    old = _p2(db, qty=0, active=False)
    _p2(db, qty=4)
    r = manager.post(f"/api/items/{old.id}/reactivate")
    assert r.status_code == 409
    db.expire_all()
    assert db.get(InventoryItem, old.id).is_active is False
    assert db.query(StockMovement).filter_by(item_id=old.id).count() == 0  # nothing half-saved


def test_sheet_rows_for_same_new_part2_slot_merge_into_one_row(manager, db):
    row = {"action": "IN", "style": "VDNEW1", "row_pos": "4", "section": "5", "level": "2", "pcs_per_box": 20,
           "quantity": 20}
    r = manager.post("/api/sheet-submit", json={"rows": [row, row]})
    assert r.status_code == 200, r.text
    rows = db.query(InventoryItem).filter_by(style="VDNEW1").all()
    assert len(rows) == 1 and rows[0].quantity == 40 and rows[0].warehouse_part == "PART_2"


def test_sheet_rows_for_same_new_line_location_stay_one_row_per_carton(manager, db):
    """Part 1 behaviour is unchanged: two cartons in one sheet = two rows (as before 1b)."""
    row = {"action": "IN", "style": "NEW1", "size": "9", "line": "2", "section": "1", "level": "4", "quantity": 20}
    r = manager.post("/api/sheet-submit", json={"rows": [row, row]})
    assert r.status_code == 200, r.text
    rows = db.query(InventoryItem).filter_by(style="NEW1").all()
    assert len(rows) == 2 and all(i.warehouse_part == "PART_1" and i.quantity == 20 for i in rows)


def test_export_default_excludes_deactivated(manager, db):
    _p2(db, style="LIVE1")
    _p2(db, style="GONE1", qty=0, active=False)
    csv_text = manager.get("/api/export-csv").text
    assert "LIVE1" in csv_text and "GONE1" not in csv_text
    assert "ACTIVE" not in csv_text.splitlines()[0]


def test_export_include_deactivated_is_admin_only(manager, admin, db):
    _p2(db, style="LIVE1")
    _p2(db, style="GONE1", qty=0, active=False)
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
