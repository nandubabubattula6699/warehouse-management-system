"""
Part 2 stock <-> locations (steps D0-D3). Part 1 (Allbirds, Lines) is never selected, linked or refused here.

  D0  empty_rows_plan / deactivate_empty_rows: deactivate active Part 2 rows at qty 0, each with a recorded
      DEACTIVATE movement. By default only rows at spots that no longer exist as active locations; rows at qty 0 at
      spots that DO exist (e.g. the "to be counted" entries) are listed and only included when ticked.
  D1  link_plan: read-only match report (row/section/level -> location code).
  D2  apply_links: set inventory_items.location_id, each with a recorded 0-pc LOCATION_LINK movement.
  D3  part2_location_id: every Part 2 write resolves its spot; with PART2_LOCATIONS_ENFORCED on, a spot that is not
      an active location is refused (409, nothing saved).
Every apply re-plans under an advisory lock and refuses unless the plan is exactly the one the admin previewed.
"""
import hashlib
import json
import os

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.location_import import stock_code
from app.models import InventoryItem, Location, StockMovement

LOCK_KEY = "part2_locations_import"  # same lock as the row-size import: one location change at a time
EMPTY_ROW_REASON = "Bulk deactivate before location linking: Part 2 row at qty 0"


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, separators=(",", ":"), default=str).encode()).hexdigest()


def _lock(db: Session):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": LOCK_KEY})


def _active_locations(db: Session) -> dict:
    return {loc.code: loc for loc in db.query(Location).filter(Location.is_active.is_(True))}


def _part2_rows(db: Session, for_update=False):
    q = (db.query(InventoryItem)
         .filter(InventoryItem.warehouse_part == "PART_2", InventoryItem.is_active.is_(True))
         .order_by(InventoryItem.id))
    return q.with_for_update().all() if for_update else q.all()


def _row_info(item: InventoryItem, code) -> dict:
    return {"id": item.id, "style": item.style, "color": item.color, "size": item.size, "location": item.location,
            "code": code or f"? Row {item.row_pos} / Sec {item.section} / Lvl {item.level}",
            "pcs_per_box": item.pcs_per_box, "quantity": item.quantity}


# ----------------------------------------------------------------------------- D0
def empty_rows_plan(db: Session) -> dict:
    locs = _active_locations(db)
    outside, inside = [], []
    for item in _part2_rows(db):
        if item.quantity != 0:
            continue
        code = stock_code(item.row_pos, item.section, item.level)
        (inside if code in locs else outside).append(_row_info(item, code))
    return {"outside": outside, "inside": inside,
            "plan_hash": _hash([[r["id"] for r in outside], [r["id"] for r in inside]])}


def deactivate_empty_rows(db: Session, plan_hash: str, include_ids, actor: str) -> dict:
    """Caller commits. Deactivates every 'outside' row plus the ticked 'inside' rows, nothing else."""
    _lock(db)
    plan = empty_rows_plan(db)
    if plan["plan_hash"] != plan_hash:
        raise LookupError("Part 2 rows or locations changed since this preview. Preview again: nothing was changed.")
    inside_ids = {r["id"] for r in plan["inside"]}
    include = set(include_ids or [])
    if not include <= inside_ids:
        raise ValueError("Only rows from the 'at existing locations' list can be ticked. Nothing was changed.")
    ids = sorted({r["id"] for r in plan["outside"]} | include)
    if not ids:
        raise ValueError("Nothing to deactivate.")
    items = (db.query(InventoryItem).filter(InventoryItem.id.in_(ids)).order_by(InventoryItem.id)
             .with_for_update().all())
    for item in items:  # re-checked under the row lock: never a row with stock, never Allbirds
        if item.quantity != 0 or item.warehouse_part != "PART_2" or not item.is_active:
            raise ValueError(f"{item.style} at {item.location} is no longer an active Part 2 row at 0. Nothing was changed.")
    for item in items:
        item.is_active = False
        db.add(StockMovement(item_id=item.id, style=item.style, change_amount=0, quantity_after=0,
                             movement_type="DEACTIVATE", reason=EMPTY_ROW_REASON, staff_name=actor))
    db.flush()
    return {"deactivated": len(items), "from_outside": len(plan["outside"]), "from_inside": len(include)}


# ----------------------------------------------------------------------------- D1 / D2
def link_plan(db: Session) -> dict:
    locs = _active_locations(db)
    by_id = {loc.id: loc.code for loc in locs.values()}
    groups = {"will_link": [], "linked_ok": [], "linked_other": [], "unmatched_stock": [], "unmatched_empty": []}
    per_row = {}
    for item in _part2_rows(db):
        code = stock_code(item.row_pos, item.section, item.level)
        loc = locs.get(code)
        info = _row_info(item, code)
        if item.location_id is not None and (loc is None or item.location_id != loc.id):
            info["linked_to"] = by_id.get(item.location_id, f"location id {item.location_id} (deactivated)")
            groups["linked_other"].append(info)
        elif loc is None:
            groups["unmatched_stock" if item.quantity else "unmatched_empty"].append(info)
        else:
            info["location_id"] = loc.id
            groups["linked_ok" if item.location_id == loc.id else "will_link"].append(info)
            row = per_row.setdefault(str(item.row_pos), {"row": str(item.row_pos), "rows": 0, "pieces": 0})
            row["rows"] += 1
            row["pieces"] += item.quantity
    linked_after = groups["will_link"] + groups["linked_ok"]
    plan = {
        **{k: v for k, v in groups.items()},
        "counts": {k: len(v) for k, v in groups.items()},
        "will_link_pieces": sum(r["quantity"] for r in groups["will_link"]),
        "linked_after": {"rows": len(linked_after), "pieces": sum(r["quantity"] for r in linked_after)},
        "per_row": sorted(per_row.values(), key=lambda r: (not r["row"].isdigit(), int(r["row"]) if r["row"].isdigit() else 0, r["row"])),
        "plan_hash": _hash([[(r["id"], r["location_id"]) for r in groups["will_link"]],
                            [r["id"] for r in groups["linked_other"]], [r["id"] for r in groups["unmatched_stock"]]]),
    }
    plan["can_apply"] = bool(groups["will_link"]) and not groups["linked_other"] and not groups["unmatched_stock"]
    return plan


def apply_links(db: Session, plan_hash: str, actor: str) -> dict:
    """Caller commits. Links exactly the previewed rows; refuses while any row with stock has no spot."""
    _lock(db)
    plan = link_plan(db)
    if plan["plan_hash"] != plan_hash:
        raise LookupError("Part 2 rows or locations changed since this preview. Preview again: nothing was changed.")
    if plan["unmatched_stock"] or plan["linked_other"]:
        raise ValueError("Rows with stock have no active location (or are linked elsewhere). Nothing was changed.")
    if not plan["will_link"]:
        raise ValueError("Nothing to link.")
    wanted = {r["id"]: (r["location_id"], r["code"]) for r in plan["will_link"]}
    items = (db.query(InventoryItem).filter(InventoryItem.id.in_(list(wanted))).order_by(InventoryItem.id)
             .with_for_update().all())
    for item in items:
        loc_id, code = wanted[item.id]
        item.location_id = loc_id
        db.add(StockMovement(item_id=item.id, style=item.style, change_amount=0, quantity_after=item.quantity,
                             movement_type="LOCATION_LINK", reason=f"Linked to location {code}", staff_name=actor))
    db.flush()
    return {"linked": len(items), "pieces": sum(i.quantity for i in items), "linked_after": plan["linked_after"]}


# ----------------------------------------------------------------------------- D3
def locations_enforced() -> bool:
    return (os.getenv("PART2_LOCATIONS_ENFORCED") or "").strip().lower() in ("1", "true", "yes", "on")


def part2_location_id(db: Session, loc_meta: dict, label: str = ""):
    """location_id for a row about to be written: None for Part 1. For Part 2 the active location of its spot; if
    there is none, None (until enforcement is switched on) or a 409 that names the spot. Nothing is guessed."""
    if loc_meta.get("warehouse_part") != "PART_2":
        return None
    code = stock_code(loc_meta.get("row_pos"), loc_meta.get("section"), loc_meta.get("level"))
    loc = (db.query(Location).filter(Location.code == code, Location.is_active.is_(True)).first()
           if code else None)
    if loc:
        return loc.id
    if not locations_enforced():
        return None
    where = code or f"Row {loc_meta.get('row_pos')} / Sec {loc_meta.get('section')} / Lvl {loc_meta.get('level')}"
    raise HTTPException(status_code=409, detail=(
        f"{label}Part 2 location {where} is not an active location. Check the row, section and level, or add the "
        f"spot on the Locations page first. Nothing was saved."))
