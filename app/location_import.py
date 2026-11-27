"""
Part 2 locations from the owner's row-size workbook (sheet "Row sizes (fill in)", built by step A).

  parse_row_sizes(xlsx bytes)  -> RowSizes (lines + errors + unconfirmed lines); reads only the file
  plan_changes(db, row_sizes)  -> what an import would do: create / reactivate / deactivate, blocked spots,
                                  stock outside the table, and a hash of exactly that plan; reads only
  apply_changes(db, ...)       -> does it in the caller's transaction, every change recorded in location_changes

Nothing is guessed: a line that is not marked OK, a bad number, or a deactivation of a spot that holds stock
makes the import refuse. Spots are never deleted, only deactivated. Part 1 (Allbirds) is not read or changed.
"""
import hashlib
import io
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.location_codes import storage_code
from app.models import InventoryItem, Location, LocationChange

SHEET = "Row sizes (fill in)"
SPECIAL_TYPES = {"R-RECV": "RECEIVING", "R-STAGE": "STAGING", "R-DAMAGE": "DAMAGE"}
MAX_ROW, MAX_SECTIONS, MAX_LEVELS = 99, 99, 9
IMPORT_LOCK = "part2_locations_import"


@dataclass
class RowSizes:
    rows: dict = field(default_factory=dict)      # row_no -> (sections, levels, ground_front_levels, ground_back_levels)
    wall: dict = field(default_factory=dict)      # "WALL_FRONT" / "WALL_BACK" -> levels
    specials: dict = field(default_factory=dict)  # code -> keep (bool)
    errors: list = field(default_factory=list)
    unconfirmed: list = field(default_factory=list)


def _int(value, what, limit, errors):
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0
    try:
        n = float(value)
    except (TypeError, ValueError):
        errors.append(f"{what}: '{value}' is not a number")
        return 0
    if n != int(n) or n < 0 or n > limit:
        errors.append(f"{what}: {value} must be a whole number from 0 to {limit}")
        return 0
    return int(n)


def parse_row_sizes(data: bytes) -> RowSizes:
    from openpyxl import load_workbook

    out = RowSizes()
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        out.errors.append("The file is not a readable .xlsx workbook.")
        return out
    if SHEET not in wb.sheetnames:
        out.errors.append(f"Sheet '{SHEET}' not found. Use the row-size workbook from step A.")
        return out

    part, confirm_col = None, None
    for values in wb[SHEET].iter_rows(values_only=True):
        cells = list(values)
        first = str(cells[0]).strip() if cells and cells[0] is not None else ""
        if first == "Row" and len(cells) > 1 and str(cells[1] or "").startswith("Shelf sections"):
            part = "rows"
            confirm_col = next((i for i, c in enumerate(cells) if str(c or "").startswith("Confirmed")), None)
            if confirm_col is None:
                out.errors.append("Column 'Confirmed: OK or correction' not found.")
                return out
            continue
        if first.startswith("Wall ("):
            part = "wall"
            continue
        if first == "Special spots":
            part = "specials"
            continue
        if first.upper().startswith("TOTAL"):
            break
        if not first or part is None or first.startswith("("):
            continue

        cell = lambda i: cells[i] if i < len(cells) else None  # noqa: E731
        confirmed = str(cell(confirm_col) or "").strip()
        if confirmed.upper() != "OK":
            out.unconfirmed.append(f"{first}: " + (f"'{confirmed}'" if confirmed else "not marked OK"))

        if part == "rows":
            row_no = _int(first, f"Row '{first}'", MAX_ROW, out.errors)
            if row_no < 1:
                out.errors.append(f"Row '{first}': row number must be 1 to {MAX_ROW}")
                continue
            if row_no in out.rows:
                out.errors.append(f"Row {row_no} appears twice")
                continue
            label = f"Row {row_no}"
            sections = _int(cell(1), f"{label} shelf sections", MAX_SECTIONS, out.errors)
            levels = _int(cell(2), f"{label} shelf levels", MAX_LEVELS, out.errors)
            gf = _int(cell(3), f"{label} ground front levels", MAX_LEVELS, out.errors)
            gb = _int(cell(4), f"{label} ground back levels", MAX_LEVELS, out.errors)
            if bool(sections) != bool(levels):
                out.errors.append(f"{label}: shelf sections and shelf levels must both be 0 or both be above 0")
            out.rows[row_no] = (sections, levels, gf, gb)
        elif part == "wall":
            area = "WALL_FRONT" if first.lower().startswith("wall front") else (
                "WALL_BACK" if first.lower().startswith("wall back") else None)
            if area is None:
                out.errors.append(f"Wall line '{first}' not recognised (expected 'Wall front' or 'Wall back')")
                continue
            out.wall[area] = _int(cell(1), f"{first} levels", MAX_LEVELS, out.errors)
        else:
            code = first.upper()
            if code not in SPECIAL_TYPES:
                out.errors.append(f"Special spot '{first}' is not known (only {', '.join(SPECIAL_TYPES)}); "
                                  "a new kind of special spot needs a code change first")
                continue
            keep = str(cell(1) or "").strip().upper()
            if keep not in ("Y", "N"):
                out.errors.append(f"Special spot {code}: Keep must be Y or N")
                continue
            out.specials[code] = keep == "Y"

    if not out.rows and not out.errors:
        out.errors.append("No row lines found under the header 'Row | Shelf sections (count) | ...'.")
    return out


def target_spots(rs: RowSizes) -> dict:
    """code -> column values for every spot the table asks for."""
    spots = {}
    for row_no, (sections, levels, gf, gb) in rs.rows.items():
        for s in range(1, sections + 1):
            for lv in range(1, levels + 1):
                spots[storage_code("SHELF", lv, row_no, s)] = dict(
                    location_type="STORAGE", area="SHELF", row_no=row_no, section_no=s, level_no=lv)
        for area, n in (("GROUND_FRONT", gf), ("GROUND_BACK", gb)):
            for lv in range(1, n + 1):
                spots[storage_code(area, lv, row_no)] = dict(
                    location_type="STORAGE", area=area, row_no=row_no, section_no=None, level_no=lv)
    for area, n in rs.wall.items():
        for lv in range(1, n + 1):
            spots[storage_code(area, lv)] = dict(
                location_type="STORAGE", area=area, row_no=None, section_no=None, level_no=lv)
    for code, keep in rs.specials.items():
        if keep:
            spots[code] = dict(location_type=SPECIAL_TYPES[code], area=None, row_no=None, section_no=None, level_no=None)
    return spots


_NUM = re.compile(r"^\d+$")


def stock_code(row_pos, section, level):
    """The new code of an existing Part 2 inventory row's spot, or None if its values don't form one."""
    row, sec, lvl = (str(v or "").strip().upper() for v in (row_pos, section, level))
    if not _NUM.match(lvl) or int(lvl) < 1:
        return None
    lv = int(lvl)
    if row == "WALL":
        return {"FRONT": storage_code("WALL_FRONT", lv), "BACK": storage_code("WALL_BACK", lv)}.get(sec)
    if not _NUM.match(row) or int(row) < 1:
        return None
    if sec == "FRONT":
        return storage_code("GROUND_FRONT", lv, int(row))
    if sec == "BACK":
        return storage_code("GROUND_BACK", lv, int(row))
    return storage_code("SHELF", lv, int(row), int(sec)) if _NUM.match(sec) and int(sec) >= 1 else None


def _part2_stock(db: Session) -> dict:
    """code (or '?row/section/level' when unmappable) -> [active rows, pieces], active Part 2 rows only."""
    stock = {}
    q = (db.query(InventoryItem.row_pos, InventoryItem.section, InventoryItem.level,
                  func.count(InventoryItem.id), func.coalesce(func.sum(InventoryItem.quantity), 0))
         .filter(InventoryItem.warehouse_part == "PART_2", InventoryItem.is_active.is_(True))
         .group_by(InventoryItem.row_pos, InventoryItem.section, InventoryItem.level))
    for row_pos, section, level, n, pcs in q:
        key = stock_code(row_pos, section, level) or f"?Row {row_pos} / Sec {section} / Lvl {level}"
        cur = stock.setdefault(key, [0, 0])
        cur[0] += int(n)
        cur[1] += int(pcs)
    return stock


def plan_changes(db: Session, rs: RowSizes) -> dict:
    target = target_spots(rs)
    existing = {loc.code: loc for loc in db.query(Location).all()}
    create = sorted(c for c in target if c not in existing)
    reactivate = sorted(c for c in target if c in existing and not existing[c].is_active)
    deactivate = sorted(c for c, loc in existing.items() if loc.is_active and c not in target)

    stock = _part2_stock(db)
    linked = dict(db.query(Location.code, func.count(InventoryItem.id))
                  .join(InventoryItem, InventoryItem.location_id == Location.id)
                  .filter(InventoryItem.is_active.is_(True)).group_by(Location.code).all())
    blocked = [f"{c}: {stock[c][1]} pcs in {stock[c][0]} active row(s)" if c in stock else f"{c}: {linked[c]} linked row(s)"
               for c in deactivate if (c in stock and stock[c][1] > 0) or linked.get(c)]
    outside = [f"{c}: {n} active row(s), {pcs} pcs" for c, (n, pcs) in sorted(stock.items()) if c not in target]

    per_row = []
    for row_no in sorted(rs.rows):
        sections, levels, gf, gb = rs.rows[row_no]
        per_row.append({"row": row_no, "shelf_sections": sections, "shelf_levels": levels, "ground_front": gf,
                        "ground_back": gb, "spots": sections * levels + gf + gb})
    for area, n in sorted(rs.wall.items()):
        per_row.append({"row": "Wall front" if area == "WALL_FRONT" else "Wall back", "levels": n, "spots": n})

    plan_hash = hashlib.sha256(json.dumps([create, reactivate, deactivate], separators=(",", ":")).encode()).hexdigest()
    return {
        "errors": rs.errors, "unconfirmed": rs.unconfirmed,
        "target_total": len(target), "existing_active": sum(1 for loc in existing.values() if loc.is_active),
        "create": create, "reactivate": reactivate, "deactivate": deactivate,
        "blocked": blocked, "stock_outside_table": outside, "per_row": per_row,
        "specials": {c: k for c, k in rs.specials.items()},
        "plan_hash": plan_hash,
        "can_apply": not rs.errors and not rs.unconfirmed and not blocked and bool(create or reactivate or deactivate),
    }


def apply_changes(db: Session, rs: RowSizes, plan_hash: str, user_id: int, source: str) -> dict:
    """Runs in the caller's transaction (caller commits). Serialized by an advisory lock; re-plans inside it and
    refuses unless the plan is exactly the one the admin previewed."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": IMPORT_LOCK})
    plan = plan_changes(db, rs)
    if plan["errors"] or plan["unconfirmed"] or plan["blocked"]:
        raise ValueError("The table has errors, unconfirmed lines or blocked deactivations: nothing was changed.")
    if plan["plan_hash"] != plan_hash:
        raise LookupError("The locations changed since this preview (or a different file was sent). "
                          "Preview again: nothing was changed.")
    target = target_spots(rs)
    changes = []
    for code in plan["create"]:
        loc = Location(code=code, created_by=user_id, **target[code])
        db.add(loc)
        changes.append((loc, "CREATE"))
    by_code = {loc.code: loc for loc in db.query(Location).filter(Location.code.in_(plan["reactivate"] + plan["deactivate"]))}
    for code, active, action in [(c, True, "REACTIVATE") for c in plan["reactivate"]] + \
                                [(c, False, "DEACTIVATE") for c in plan["deactivate"]]:
        loc = by_code[code]
        loc.is_active = active
        loc.updated_by = user_id
        loc.updated_at = func.now()
        loc.row_version = Location.row_version + 1
        changes.append((loc, action))
    db.flush()
    for loc, action in changes:
        db.add(LocationChange(location_id=loc.id, action=action, source=source[:255], changed_by=user_id))
    db.flush()
    return {"created": len(plan["create"]), "reactivated": len(plan["reactivate"]),
            "deactivated": len(plan["deactivate"]), "active_now": plan["target_total"]}
