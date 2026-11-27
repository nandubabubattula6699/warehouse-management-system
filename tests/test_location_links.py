"""Part 2 locations D0-D3: deactivate empty rows, link stock to spots, refuse writes to spots that don't exist."""
import pytest
from sqlalchemy import text

from app.models import InventoryItem, Location, StockMovement
from tests.conftest import _logged_in, make_user

SPOTS = [("R4-S1-L1", "SHELF", 4, 1, 1), ("R4-S1-L2", "SHELF", 4, 1, 2), ("R15-GF-L1", "GROUND_FRONT", 15, None, 1),
         ("W-SB-L1", "WALL_BACK", None, None, 1)]


@pytest.fixture
def admin(db):
    return _logged_in(db, "linkadmin", "ADMIN")


@pytest.fixture
def spots(db):
    uid = make_user(db, "spotmaker", role="ADMIN").id
    for code, area, r, s, lv in SPOTS:
        db.add(Location(code=code, location_type="STORAGE", area=area, row_no=r, section_no=s, level_no=lv, created_by=uid))
    db.add(Location(code="R12-GF-L1", location_type="STORAGE", area="GROUND_FRONT", row_no=12, level_no=1,
                    created_by=uid, is_active=False))  # deactivated spot: does not count
    db.commit()
    return {loc.code: loc.id for loc in db.query(Location)}


def p2(db, style, row, sec, lvl, qty, pcs=8, active=True):
    item = InventoryItem(style=style, color="BLACK", size="OS", row_pos=row, section=sec, level=lvl, pcs_per_box=pcs,
                         warehouse_part="PART_2", location=f"Row {row} • Sec {sec} • Lvl {lvl}", quantity=qty,
                         is_active=active)
    db.add(item)
    db.commit()
    return item


def p1(db, qty=0):
    item = InventoryItem(style="TB1WJBK", line="2", section="1", level="4", warehouse_part="PART_1",
                         location="Line 2 • Sec 1 • Lvl 4", quantity=qty)
    db.add(item)
    db.commit()
    return item


# ----------------------------------------------------------------------------- D0
def test_empty_rows_preview_splits_old_spots_from_existing_spots(admin, db, spots):
    old = p2(db, "OLD", "12", "FRONT", "1", 0)      # spot deactivated / no longer exists
    gone = p2(db, "GONE", "7", "8", "14", 0)        # spot never existed (level 14)
    tbc = p2(db, "TOCOUNT", "4", "1", "1", 0)       # qty 0 at an existing spot ("to be counted")
    p2(db, "STOCK", "4", "1", "2", 24)              # has stock: never listed
    p1(db, qty=0)                                   # Allbirds at 0: never listed
    plan = admin.get("/api/locations/empty-rows/preview").json()
    assert [r["id"] for r in plan["outside"]] == [old.id, gone.id]
    assert [r["id"] for r in plan["inside"]] == [tbc.id]


def test_empty_rows_apply_default_and_ticked(admin, db, spots):
    old = p2(db, "OLD", "12", "FRONT", "1", 0)
    tbc = p2(db, "TOCOUNT", "4", "1", "1", 0)
    allbirds = p1(db, qty=0)
    plan = admin.get("/api/locations/empty-rows/preview").json()
    r = admin.post("/api/locations/empty-rows/apply", json={"plan_hash": plan["plan_hash"]})
    assert r.status_code == 200 and r.json()["deactivated"] == 1, r.text
    db.expire_all()
    assert db.get(InventoryItem, old.id).is_active is False
    assert db.get(InventoryItem, tbc.id).is_active is True          # not ticked: stays
    assert db.get(InventoryItem, allbirds.id).is_active is True
    mv = db.query(StockMovement).filter_by(item_id=old.id).one()
    assert (mv.movement_type, mv.change_amount, mv.staff_name) == ("DEACTIVATE", 0, "Linkadmin Person")

    plan = admin.get("/api/locations/empty-rows/preview").json()
    r = admin.post("/api/locations/empty-rows/apply", json={"plan_hash": plan["plan_hash"], "include_ids": [tbc.id]})
    assert r.status_code == 200 and r.json()["deactivated"] == 1
    db.expire_all()
    assert db.get(InventoryItem, tbc.id).is_active is False


def test_empty_rows_refuses_foreign_ids_and_stale_preview(admin, db, spots):
    p2(db, "OLD", "12", "FRONT", "1", 0)
    stock = p2(db, "STOCK", "4", "1", "2", 24)
    allbirds = p1(db, qty=0)
    plan = admin.get("/api/locations/empty-rows/preview").json()
    for bad in ([stock.id], [allbirds.id]):
        assert admin.post("/api/locations/empty-rows/apply",
                          json={"plan_hash": plan["plan_hash"], "include_ids": bad}).status_code == 400
    p2(db, "NEW-EMPTY", "7", "1", "9", 0)  # something changed after the preview
    assert admin.post("/api/locations/empty-rows/apply", json={"plan_hash": plan["plan_hash"]}).status_code == 409
    assert db.query(InventoryItem).filter_by(is_active=False).count() == 0


# ----------------------------------------------------------------------------- D1 / D2
def test_link_report_and_apply(admin, db, spots):
    a = p2(db, "A", "4", "1", "1", 24)
    b = p2(db, "B", "15", "FRONT", "1", 10)
    w = p2(db, "W", "WALL", "BACK", "1", 9)
    empty_old = p2(db, "E", "12", "FRONT", "1", 0)
    allbirds = p1(db, qty=20)
    plan = admin.get("/api/locations/link/preview").json()
    assert plan["counts"] == {"will_link": 3, "linked_ok": 0, "linked_other": 0, "unmatched_stock": 0, "unmatched_empty": 1}
    assert plan["will_link_pieces"] == 43 and plan["linked_after"] == {"rows": 3, "pieces": 43} and plan["can_apply"]
    csv = admin.get("/api/locations/link/report.csv")
    assert csv.status_code == 200 and "unmatched_empty" in csv.text and "R4-S1-L1" in csv.text

    before = {i.id: i.quantity for i in db.query(InventoryItem)}
    r = admin.post("/api/locations/link/apply", json={"plan_hash": plan["plan_hash"]})
    assert r.status_code == 200, r.text
    assert r.json()["linked"] == 3 and r.json()["pieces"] == 43
    db.expire_all()
    assert db.get(InventoryItem, a.id).location_id == spots["R4-S1-L1"]
    assert db.get(InventoryItem, b.id).location_id == spots["R15-GF-L1"]
    assert db.get(InventoryItem, w.id).location_id == spots["W-SB-L1"]
    assert db.get(InventoryItem, empty_old.id).location_id is None
    assert db.get(InventoryItem, allbirds.id).location_id is None
    assert {i.id: i.quantity for i in db.query(InventoryItem)} == before   # no quantity changed
    links = db.query(StockMovement).filter_by(movement_type="LOCATION_LINK").all()
    assert len(links) == 3 and {m.change_amount for m in links} == {0} and {m.staff_name for m in links} == {"Linkadmin Person"}
    again = admin.get("/api/locations/link/preview").json()
    assert again["counts"]["will_link"] == 0 and again["counts"]["linked_ok"] == 3 and not again["can_apply"]


def test_link_refused_while_stock_has_no_spot(admin, db, spots):
    p2(db, "A", "4", "1", "1", 24)
    p2(db, "LOST", "15", "2", "1", 20)  # shelf spot not in the table, with stock
    plan = admin.get("/api/locations/link/preview").json()
    assert plan["counts"]["unmatched_stock"] == 1 and plan["can_apply"] is False
    assert admin.post("/api/locations/link/apply", json={"plan_hash": plan["plan_hash"]}).status_code == 400
    assert db.query(InventoryItem).filter(InventoryItem.location_id.isnot(None)).count() == 0


def test_link_stale_report_refused(admin, db, spots):
    p2(db, "A", "4", "1", "1", 24)
    plan = admin.get("/api/locations/link/preview").json()
    p2(db, "B", "4", "1", "2", 8)
    assert admin.post("/api/locations/link/apply", json={"plan_hash": plan["plan_hash"]}).status_code == 409


@pytest.mark.parametrize("role", ["MANAGER", "STAFF"])
def test_d0_d2_admin_only(db, spots, role):
    c = _logged_in(db, "nolink", role)
    assert c.get("/api/locations/empty-rows/preview").status_code == 403
    assert c.post("/api/locations/empty-rows/apply", json={"plan_hash": "x"}).status_code == 403
    assert c.get("/api/locations/link/preview").status_code == 403
    assert c.get("/api/locations/link/report.csv").status_code == 403
    assert c.post("/api/locations/link/apply", json={"plan_hash": "x"}).status_code == 403


# ----------------------------------------------------------------------------- D3
@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setenv("PART2_LOCATIONS_ENFORCED", "1")


def _new_item(style, row, sec, lvl, qty=8, line=None):
    return {"style": style, "color": "BLACK", "size": "OS", "row_pos": row, "section": sec, "level": lvl, "line": line,
            "pcs_per_box": 8, "quantity": qty, "location": "set by the app"}


def test_writes_link_automatically_before_enforcement(manager, db, spots, monkeypatch):
    monkeypatch.delenv("PART2_LOCATIONS_ENFORCED", raising=False)
    r = manager.post("/api/items", json=_new_item("VDBP-039", "4", "1", "1"))
    assert r.status_code == 201, r.text
    assert db.get(InventoryItem, r.json()["id"]).location_id == spots["R4-S1-L1"]
    r = manager.post("/api/items", json=_new_item("VDBP-040", "7", "40", "1"))  # spot missing: allowed, unlinked
    assert r.status_code == 201 and db.get(InventoryItem, r.json()["id"]).location_id is None


def test_enforced_create_sheet_receiving_refuse_missing_spot(manager, db, spots, enforced):
    r = manager.post("/api/items", json=_new_item("VDBP-040", "7", "40", "1"))
    assert r.status_code == 409 and "R7-S40-L1 is not an active location" in r.json()["detail"]
    r = manager.post("/api/sheet-submit", json={"rows": [
        {"action": "IN", **_new_item("VDBP-041", "4", "1", "1")},
        {"action": "IN", **_new_item("VDBP-042", "12", "FRONT", "1")},   # deactivated spot
    ]})
    assert r.status_code == 409 and r.json()["detail"].startswith("Row #2 (VDBP-042): ")
    assert db.query(InventoryItem).count() == 0                           # whole sheet rolled back
    r = manager.post("/api/receiving", json={"style": "VDBP-043", "row_pos": "15", "section": "Q", "level": "1",
                                              "quantity": 5})
    assert r.status_code == 409 and "Row 15 / Sec Q / Lvl 1" in r.json()["detail"]
    r = manager.post("/api/receiving", json={"style": "VDBP-043", "row_pos": "15", "section": "FRONT", "level": "1",
                                              "quantity": 5})
    assert r.status_code == 200 and db.query(InventoryItem).one().location_id == spots["R15-GF-L1"]


def test_enforced_edit_and_reactivate(manager, db, spots, enforced):
    item = p2(db, "VDBP-039", "4", "1", "1", 8)
    body = {"style": "VDBP-039", "color": "BLACK", "size": "OS", "row_pos": "4", "section": "1", "level": "2",
            "pcs_per_box": 8, "quantity": 8}
    r = manager.put(f"/api/items/{item.id}", json=body)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(InventoryItem, item.id).location_id == spots["R4-S1-L2"]
    r = manager.put(f"/api/items/{item.id}", json={**body, "section": "9"})
    assert r.status_code == 409
    db.expire_all()
    assert db.get(InventoryItem, item.id).section == "1"                    # nothing saved
    old = p2(db, "OLDROW", "12", "FRONT", "1", 0, active=False)
    assert manager.post(f"/api/items/{old.id}/reactivate").status_code == 409


def test_enforced_inbound_approval_refuses_missing_spot(staff, db, spots, enforced):
    admin = _logged_in(db, "inbadmin", "ADMIN")
    r = staff.post("/api/inbound/shipments", json={"items": [
        {"style": "VDBP-050", "row_pos": "4", "section": "1", "level": "1", "quantity": 8},
        {"style": "VDBP-051", "row_pos": "7", "section": "40", "level": "1", "quantity": 8},
    ]})
    assert r.status_code == 200, r.text
    r = admin.post(f"/api/inbound/shipments/{r.json()['id']}/approve", json={})
    assert r.status_code == 409 and "VDBP-051" in r.json()["detail"]
    assert db.query(InventoryItem).count() == 0


def test_enforcement_never_touches_allbirds(manager, db, spots, enforced):
    r = manager.post("/api/items", json={"style": "TB1WJBK", "line": "2", "section": "1", "level": "4", "quantity": 20,
                                          "location": "set by the app"})
    assert r.status_code == 201 and db.get(InventoryItem, r.json()["id"]).location_id is None
    r = manager.post("/api/receiving", json={"style": "TB1WJBK", "line": "2", "section": "1", "level": "4", "quantity": 5})
    assert r.status_code == 200
    assert db.execute(text("SELECT count(*) FROM inventory_items WHERE location_id IS NOT NULL")).scalar() == 0


# ----------------------------------------------------------------------------- D2 undo (unlink)
def _link_all(admin):
    plan = admin.get("/api/locations/link/preview").json()
    r = admin.post("/api/locations/link/apply", json={"plan_hash": plan["plan_hash"]})
    assert r.status_code == 200, r.text
    return r.json()["run"]


def test_unlink_last_run_skips_rows_changed_since(admin, manager, db, spots):
    a = p2(db, "A", "4", "1", "1", 24)
    b = p2(db, "B", "15", "FRONT", "1", 10)
    moved = p2(db, "M", "4", "1", "1", 8, pcs=9)
    run = _link_all(admin)
    runs = admin.get("/api/locations/unlink/runs").json()
    assert runs[0]["run"] == run and runs[0]["rows"] == 3 and runs[0]["by"] == "Linkadmin Person"
    # one row is moved to another spot after the run: its link now comes from that edit
    body = {"style": "M", "color": "BLACK", "size": "OS", "row_pos": "4", "section": "1", "level": "2",
            "pcs_per_box": 9, "quantity": 8}
    assert manager.put(f"/api/items/{moved.id}", json=body).status_code == 200

    plan = admin.get("/api/locations/unlink/preview", params={"run": run}).json()
    assert [r["id"] for r in plan["will_unlink"]] == [a.id, b.id] and plan["pieces"] == 34
    assert [(r["id"], r["now"]) for r in plan["skipped"]] == [(moved.id, "R4-S1-L2")]
    before = {i.id: i.quantity for i in db.query(InventoryItem)}
    r = admin.post("/api/locations/unlink/apply", json={"plan_hash": plan["plan_hash"], "run": run})
    assert r.status_code == 200 and r.json() == {"status": "ok", "unlinked": 2, "pieces": 34, "skipped": 1}
    db.expire_all()
    assert db.get(InventoryItem, a.id).location_id is None and db.get(InventoryItem, b.id).location_id is None
    assert db.get(InventoryItem, moved.id).location_id == spots["R4-S1-L2"]
    assert {i.id: i.quantity for i in db.query(InventoryItem)} == before
    mv = db.query(StockMovement).filter_by(movement_type="LOCATION_UNLINK").order_by(StockMovement.id).all()
    assert [(m.item_id, m.change_amount, m.staff_name) for m in mv] == [(a.id, 0, "Linkadmin Person"), (b.id, 0, "Linkadmin Person")]
    assert mv[0].reason == f"Unlinked from location R4-S1-L1 (undo of link run {run})"
    # the rows can be linked again by a new D2 run
    assert admin.get("/api/locations/link/preview").json()["counts"]["will_link"] == 2


def test_unlink_one_location_code(admin, db, spots):
    a = p2(db, "A", "4", "1", "1", 24)
    b = p2(db, "B", "15", "FRONT", "1", 10)
    _link_all(admin)
    plan = admin.get("/api/locations/unlink/preview", params={"code": "r15-gf-l1"}).json()
    assert [r["id"] for r in plan["will_unlink"]] == [b.id]
    r = admin.post("/api/locations/unlink/apply", json={"plan_hash": plan["plan_hash"], "code": "r15-gf-l1"})
    assert r.status_code == 200 and r.json()["unlinked"] == 1
    db.expire_all()
    assert db.get(InventoryItem, a.id).location_id == spots["R4-S1-L1"] and db.get(InventoryItem, b.id).location_id is None


def test_unlink_refuses_stale_bad_and_empty_requests(admin, db, spots):
    p2(db, "A", "4", "1", "1", 24)
    run = _link_all(admin)
    plan = admin.get("/api/locations/unlink/preview", params={"run": run}).json()
    admin.post("/api/locations/unlink/apply", json={"plan_hash": plan["plan_hash"], "run": run})
    assert admin.post("/api/locations/unlink/apply", json={"plan_hash": plan["plan_hash"], "run": run}).status_code == 409
    assert admin.get("/api/locations/unlink/preview").status_code == 400
    assert admin.get("/api/locations/unlink/preview", params={"run": run, "code": "R4-S1-L1"}).status_code == 400
    assert admin.get("/api/locations/unlink/preview", params={"run": "000000000000"}).status_code == 404
    assert admin.get("/api/locations/unlink/preview", params={"code": "R1-S1-L1"}).status_code == 404
    empty = admin.get("/api/locations/unlink/preview", params={"code": "W-SB-L1"}).json()
    assert empty["can_apply"] is False
    assert admin.post("/api/locations/unlink/apply", json={"plan_hash": empty["plan_hash"], "code": "W-SB-L1"}).status_code == 400


@pytest.mark.parametrize("role", ["MANAGER", "STAFF"])
def test_unlink_admin_only(db, spots, role):
    c = _logged_in(db, "nounlink", role)
    assert c.get("/api/locations/unlink/runs").status_code == 403
    assert c.get("/api/locations/unlink/preview", params={"code": "R4-S1-L1"}).status_code == 403
    assert c.post("/api/locations/unlink/apply", json={"plan_hash": "x", "code": "R4-S1-L1"}).status_code == 403
