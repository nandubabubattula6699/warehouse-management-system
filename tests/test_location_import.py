"""Part 2 locations step C: row-size workbook -> preview (read only) -> apply exactly that preview, recorded."""
import base64
import io

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.location_import import parse_row_sizes, stock_code
from app.models import InventoryItem, Location, LocationChange, StockMovement, WarehouseUser
from tests.conftest import _logged_in

HEADER = ["Row", "Shelf sections (count)", "Shelf levels", "Ground front levels", "Ground back levels",
          "Spots this creates", "What the data shows", "Unsure? (why)", "Confirmed: OK or correction"]


def workbook(rows, wall=(0, 2), specials=(("R-RECV", "Y"), ("R-STAGE", "Y"), ("R-DAMAGE", "Y")), ok="OK"):
    """Same layout as C:\\WMS-backups\\part2_row_sizes_2026-11-26.xlsx. rows: (row, sections, levels, gf, gb)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Row sizes (fill in)"
    ws.append(["Part 2 row sizes - title"])
    ws.append(["note"])
    ws.append(["codes"])
    ws.append([])
    ws.append(HEADER)
    for r in rows:
        ws.append([*r, "=formula", "data", "", ok])
    ws.append([])
    ws.append(["Wall (no section numbers)", "Levels", None, None, None, "Spots", "data", "unsure", "Confirmed: OK or correction"])
    ws.append(["Wall front (W-SF-L<level>)", wall[0], None, None, None, "=B", "", "", ok])
    ws.append(["Wall back (W-SB-L<level>)", wall[1], None, None, None, "=B", "", "", ok])
    ws.append([])
    ws.append(["Special spots", "Keep? (Y/N)", None, None, None, "Spots", "Purpose", None, "Confirmed: OK or correction"])
    for code, keep in specials:
        ws.append([code, keep, None, None, None, "=IF", "purpose", None, ok])
    ws.append(["(add more here, e.g. returns)"])
    ws.append([])
    ws.append(["TOTAL spots", None, None, None, None, "=SUM"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def payload(data, plan_hash=None, name="part2_row_sizes.xlsx"):
    body = {"filename": name, "data_base64": "data:application/octet-stream;base64," + base64.b64encode(data).decode()}
    if plan_hash:
        body["plan_hash"] = plan_hash
    return body


SMALL = [(1, 0, 0, 2, 2), (4, 3, 4, 0, 0)]  # row 1 ground only (4 spots), row 4 shelf 3x4 (12 spots)


@pytest.fixture
def admin(db):
    return _logged_in(db, "locadmin", "ADMIN")


def _preview(client, data):
    r = client.post("/api/locations/import/preview", json=payload(data))
    assert r.status_code == 200, r.text
    return r.json()


def _apply(client, data, plan):
    return client.post("/api/locations/import/apply", json=payload(data, plan["plan_hash"]))


def test_parse_reads_rows_wall_and_specials():
    rs = parse_row_sizes(workbook(SMALL, wall=(1, 2)))
    assert rs.errors == [] and rs.unconfirmed == []
    assert rs.rows == {1: (0, 0, 2, 2), 4: (3, 4, 0, 0)}
    assert rs.wall == {"WALL_FRONT": 1, "WALL_BACK": 2}
    assert rs.specials == {"R-RECV": True, "R-STAGE": True, "R-DAMAGE": True}


@pytest.mark.parametrize("rows,expect", [
    ([(4, 3, 0, 0, 0)], "both be 0 or both be above 0"),
    ([(4, "three", 4, 0, 0)], "not a number"),
    ([(4, 3, 12, 0, 0)], "from 0 to 9"),
    ([(4, 3, 4, 0, 0), (4, 2, 4, 0, 0)], "appears twice"),
    ([(4, 2.5, 4, 0, 0)], "whole number"),
])
def test_parse_refuses_bad_numbers(rows, expect):
    assert any(expect in e for e in parse_row_sizes(workbook(rows)).errors)


def test_parse_refuses_unknown_special_and_non_xlsx():
    assert any("not known" in e for e in parse_row_sizes(workbook(SMALL, specials=(("R-RETURNS", "Y"),))).errors)
    assert parse_row_sizes(b"not a workbook").errors


def test_stock_code_maps_old_values_to_new_codes():
    assert stock_code("3", "5", "2") == "R3-S5-L2"
    assert stock_code("3", "FRONT", "1") == "R3-GF-L1"
    assert stock_code("3", "BACK", "2") == "R3-GB-L2"
    assert stock_code("WALL", "BACK", "1") == "W-SB-L1"
    assert stock_code("WALL", "FRONT", "2") == "W-SF-L2"
    assert stock_code("7", "8", "14") == "R7-S8-L14"  # outside a 4-level table: reported, never guessed
    assert stock_code("15", "Q", "1") is None


def test_preview_changes_nothing_and_shows_the_plan(admin, db):
    plan = _preview(admin, workbook(SMALL, wall=(0, 2)))
    assert plan["target_total"] == 4 + 12 + 2 + 3
    assert plan["create_count"] == 21 and plan["deactivate"] == [] and plan["can_apply"] is True
    assert db.query(Location).count() == 0 and db.query(LocationChange).count() == 0


def test_unconfirmed_lines_block_apply(admin, db):
    data = workbook(SMALL, ok="")
    plan = _preview(admin, data)
    assert plan["can_apply"] is False and len(plan["unconfirmed"]) == 2 + 2 + 3
    r = admin.post("/api/locations/import/apply", json=payload(data, plan["plan_hash"]))
    assert r.status_code == 400
    assert db.query(Location).count() == 0


def test_apply_creates_exactly_the_preview_and_records_every_change(admin, db):
    data = workbook(SMALL, wall=(0, 2))
    plan = _preview(admin, data)
    r = _apply(admin, data, plan)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 21
    codes = {c for (c,) in db.query(Location.code)}
    assert {"R1-GF-L1", "R1-GB-L2", "R4-S3-L4", "W-SB-L2", "R-RECV", "R-DAMAGE"} <= codes and len(codes) == 21
    admin_id = db.query(WarehouseUser.id).filter_by(username="locadmin").scalar()
    changes = db.query(LocationChange).all()
    assert len(changes) == 21 and {c.action for c in changes} == {"CREATE"}
    assert {c.changed_by for c in changes} == {admin_id} and all("part2_row_sizes.xlsx" in c.source for c in changes)
    # Same file again: nothing to do.
    again = _preview(admin, data)
    assert again["create_count"] == 0 and again["deactivate"] == [] and again["can_apply"] is False


def test_smaller_table_deactivates_and_bigger_reactivates(admin, db):
    big = workbook(SMALL)
    _apply(admin, big, _preview(admin, big))
    small = workbook([(1, 0, 0, 2, 2), (4, 2, 4, 0, 0)])  # row 4: 3 -> 2 sections
    plan = _preview(admin, small)
    assert plan["deactivate"] == [f"R4-S3-L{lv}" for lv in range(1, 5)]
    assert _apply(admin, small, plan).status_code == 200
    db.expire_all()
    assert db.query(Location).filter_by(is_active=False).count() == 4
    assert db.query(Location).count() == 21 + 0  # never deleted
    plan = _preview(admin, big)
    assert plan["reactivate"] == [f"R4-S3-L{lv}" for lv in range(1, 5)] and plan["create_count"] == 0
    assert _apply(admin, big, plan).status_code == 200
    actions = [a for (a,) in db.query(LocationChange.action).order_by(LocationChange.id)]
    assert actions.count("DEACTIVATE") == 4 and actions.count("REACTIVATE") == 4
    db.expire_all()
    assert db.query(Location).filter_by(code="R4-S3-L1").one().row_version == 3


def test_spot_with_stock_cannot_be_deactivated(admin, db):
    big = workbook(SMALL)
    _apply(admin, big, _preview(admin, big))
    db.add(InventoryItem(style="VDBP-039", color="CAMO", size="OS", row_pos="4", section="3", level="2",
                         warehouse_part="PART_2", location="Row 4 • Sec 3 • Lvl 2", quantity=24, pcs_per_box=8))
    db.commit()
    small = workbook([(1, 0, 0, 2, 2), (4, 2, 4, 0, 0)])
    plan = _preview(admin, small)
    assert plan["blocked"] == ["R4-S3-L2: 24 pcs in 1 active row(s)"] and plan["can_apply"] is False
    assert admin.post("/api/locations/import/apply", json=payload(small, plan["plan_hash"])).status_code == 400
    db.expire_all()
    assert db.query(Location).filter_by(is_active=False).count() == 0


def test_stock_outside_the_table_is_listed_not_guessed(admin, db):
    db.add(InventoryItem(style="VDSB-2118", color="BLACK", size="OS", row_pos="7", section="8", level="14",
                         warehouse_part="PART_2", location="Row 7 • Sec 8 • Lvl 14", quantity=0, pcs_per_box=24))
    db.commit()
    plan = _preview(admin, workbook(SMALL))
    assert plan["stock_outside_table"] == ["R7-S8-L14: 1 active row(s), 0 pcs"]


def test_stale_preview_is_refused(admin, db):
    data = workbook(SMALL)
    plan = _preview(admin, data)
    other = workbook([(1, 0, 0, 2, 2)])
    _apply(admin, other, _preview(admin, other))  # someone else changed the locations meanwhile
    r = _apply(admin, data, plan)
    assert r.status_code == 409 and "Preview again" in r.json()["detail"]


def test_apply_needs_a_preview_hash(admin):
    r = admin.post("/api/locations/import/apply", json=payload(workbook(SMALL)))
    assert r.status_code == 400


def test_import_touches_no_inventory_row(admin, db):
    db.add(InventoryItem(style="TB1WJBK", line="2", section="1", level="4", warehouse_part="PART_1",
                         location="Line 2 • Sec 1 • Lvl 4", quantity=20))
    db.add(InventoryItem(style="VDBP-039", row_pos="4", section="1", level="1", warehouse_part="PART_2",
                         location="Row 4 • Sec 1 • Lvl 1", quantity=8))
    db.commit()
    before = db.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall()
    data = workbook(SMALL)
    assert _apply(admin, data, _preview(admin, data)).status_code == 200
    assert db.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall() == before
    assert db.query(StockMovement).count() == 0


@pytest.mark.parametrize("role", ["MANAGER", "STAFF"])
def test_only_admins(db, role):
    client = _logged_in(db, "notadmin", role)
    assert client.post("/api/locations/import/preview", json=payload(workbook(SMALL))).status_code == 403
    assert client.post("/api/locations/import/apply", json=payload(workbook(SMALL), "x")).status_code == 403
    assert client.get("/api/locations/summary").status_code == 403


def test_location_changes_is_append_only(admin, db):
    data = workbook(SMALL)
    _apply(admin, data, _preview(admin, data))
    for sql in ("UPDATE location_changes SET source = 'x'", "DELETE FROM location_changes"):
        with pytest.raises(Exception, match="append-only"):
            db.execute(text(sql))
        db.rollback()
    assert db.query(LocationChange).count() == 21
