"""Part 2 locations (migration 0004): codes always agree with their coordinates, Allbirds can never be linked."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.location_codes import storage_code
from app.models import InventoryItem, Location
from tests.conftest import make_user


@pytest.fixture
def admin_id(db):
    return make_user(db, "locadmin", role="ADMIN").id


def _loc(db, user_id, code, location_type="STORAGE", area=None, row=None, section=None, level=None):
    loc = Location(code=code, location_type=location_type, area=area, row_no=row, section_no=section,
                   level_no=level, created_by=user_id)
    db.add(loc)
    db.commit()
    return loc


def _refused(db, user_id, **kw):
    with pytest.raises(IntegrityError):
        _loc(db, user_id, **kw)
    db.rollback()


VALID = [
    dict(code="R3-S5-L2", area="SHELF", row=3, section=5, level=2),
    dict(code="R3-GF-L1", area="GROUND_FRONT", row=3, level=1),
    dict(code="R3-GB-L2", area="GROUND_BACK", row=3, level=2),
    dict(code="W-SF-L1", area="WALL_FRONT", level=1),
    dict(code="W-SB-L2", area="WALL_BACK", level=2),
    dict(code="R16-S27-L4", area="SHELF", row=16, section=27, level=4),
]


@pytest.mark.parametrize("spot", VALID, ids=[s["code"] for s in VALID])
def test_valid_storage_codes_are_accepted(db, admin_id, spot):
    loc = _loc(db, admin_id, **spot)
    assert loc.is_active is True and loc.created_at is not None and loc.row_version == 1
    assert storage_code(spot["area"], spot["level"], spot.get("row"), spot.get("section")) == spot["code"]


@pytest.mark.parametrize("code,ltype", [("R-RECV", "RECEIVING"), ("R-STAGE", "STAGING"), ("R-DAMAGE", "DAMAGE")])
def test_special_spots_have_no_coordinates(db, admin_id, code, ltype):
    _loc(db, admin_id, code=code, location_type=ltype)
    _refused(db, admin_id, code=code + "X", location_type=ltype, level=1)


BAD = [
    ("code disagrees with level", dict(code="R3-S5-L3", area="SHELF", row=3, section=5, level=2)),
    ("level 0", dict(code="R3-S5-L0", area="SHELF", row=3, section=5, level=0)),
    ("shelf without level", dict(code="R3-S5-L", area="SHELF", row=3, section=5)),
    ("shelf without section", dict(code="R3-S-L1", area="SHELF", row=3, level=1)),
    ("ground with a section", dict(code="R3-GF-L1", area="GROUND_FRONT", row=3, section=5, level=1)),
    ("ground front code on ground back", dict(code="R3-GF-L1", area="GROUND_BACK", row=3, level=1)),
    ("wall with a row", dict(code="W-SF-L1", area="WALL_FRONT", row=3, level=1)),
    ("wall with a section number (old format)", dict(code="W-S12-L1", area="WALL_FRONT", section=12, level=1)),
    ("wall back code on wall front", dict(code="W-SB-L1", area="WALL_FRONT", level=1)),
    ("lower-case code", dict(code="r3-s5-l2", area="SHELF", row=3, section=5, level=2)),
    ("unknown area", dict(code="R3-S5-L2", area="RACK", row=3, section=5, level=2)),
    ("storage without area", dict(code="R3-S5-L2", row=3, section=5, level=2)),
    ("special with a storage-looking code", dict(code="R3-S5-L2", location_type="RECEIVING")),
    ("unknown type", dict(code="R-RETURNS", location_type="RETURNS")),
]


@pytest.mark.parametrize("why,spot", BAD, ids=[b[0] for b in BAD])
def test_inconsistent_codes_are_refused(db, admin_id, why, spot):
    _refused(db, admin_id, **spot)


def test_code_is_unique(db, admin_id):
    _loc(db, admin_id, **VALID[0])
    _refused(db, admin_id, **VALID[0])


def test_created_by_is_required(db):
    with pytest.raises(IntegrityError):
        db.add(Location(code="R3-S5-L2", location_type="STORAGE", area="SHELF", row_no=3, section_no=5, level_no=2))
        db.commit()
    db.rollback()


def test_part2_row_can_be_linked_but_allbirds_never(db, admin_id):
    loc = _loc(db, admin_id, **VALID[0])
    p2 = InventoryItem(style="VDBP-039", row_pos="3", section="5", level="2", warehouse_part="PART_2",
                       location="Row 3 • Sec 5 • Lvl 2", quantity=8, location_id=loc.id)
    db.add(p2)
    db.commit()
    assert db.get(InventoryItem, p2.id).location_id == loc.id

    p1 = InventoryItem(style="TB1WJBK", line="2", section="1", level="4", warehouse_part="PART_1",
                       location="Line 2 • Sec 1 • Lvl 4", quantity=20, location_id=loc.id)
    db.add(p1)
    with pytest.raises(IntegrityError, match="ck_inventory_items_location_part2_only"):
        db.commit()
    db.rollback()

    # Moving a linked Part 2 row into Part 1 is refused too.
    db.execute(text("SAVEPOINT s"))
    with pytest.raises(Exception, match="ck_inventory_items_location_part2_only"):
        db.execute(text("UPDATE inventory_items SET warehouse_part = 'PART_1' WHERE id = :i"), {"i": p2.id})
    db.rollback()


def test_location_with_linked_stock_cannot_be_deleted(db, admin_id):
    loc = _loc(db, admin_id, **VALID[0])
    db.add(InventoryItem(style="VDBP-039", warehouse_part="PART_2", row_pos="3", section="5", level="2",
                         location="Row 3 • Sec 5 • Lvl 2", quantity=8, location_id=loc.id))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM locations WHERE id = :i"), {"i": loc.id})
        db.commit()
    db.rollback()
