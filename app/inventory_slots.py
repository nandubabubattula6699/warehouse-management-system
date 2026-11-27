"""
"One active row per slot" rule (migration 0003) - Part 2 (VD & VO, Rows) ONLY.

Part 1 (Allbirds, Lines) is deliberately NOT covered: it keeps one row per carton, so several
active rows with the same style/color/size at the same Line location are normal there.

A Part 2 slot is location (row, section, level) + style + color + size + pack size (pcs per box),
normalized the way the app matches rows when stock comes in (upper-case style/color/size, color
default STANDARD, size default OS, empty string for a missing coordinate, 0 for an unknown pack
size). Box # is not part of the slot (in Part 2 it is used as a carton count, e.g. "Box 5" = 5
cartons). Only ACTIVE rows count: deactivated rows keep their history and never block a new row.
"""
from sqlalchemy import text

ACTIVE_SLOT_INDEX = "uq_inventory_items_part2_active_slot"

# Rows the rule applies to (the partial-index WHERE clause).
ACTIVE_SLOT_WHERE = "is_active AND warehouse_part = 'PART_2'"

# Expressions of the unique index, in order (also used for the duplicate report).
ACTIVE_SLOT_EXPRESSIONS = (
    "coalesce(row_pos, '')",
    "coalesce(section, '')",
    "coalesce(level, '')",
    "upper(style)",
    "upper(coalesce(color, 'STANDARD'))",
    "upper(coalesce(size, 'OS'))",
    "coalesce(pcs_per_box, 0)",
)

ACTIVE_SLOT_CONFLICT_MESSAGE = (
    "Part 2: an active row already exists for this location, style, color, size and pack size. "
    "Add the pieces to that row instead (Adj / sheet IN), or deactivate one of them first. Nothing was saved."
)


def find_duplicate_active_slots(conn, limit: int | None = None):
    """Read-only. Part 2 groups of ACTIVE rows that share a slot: list of dicts, biggest groups first."""
    key = ", ".join(ACTIVE_SLOT_EXPRESSIONS)
    sql = (
        f"SELECT {key}, count(*) AS n, array_agg(id ORDER BY id) AS ids, "
        f"array_agg(quantity ORDER BY id) AS quantities, min(location) AS location, "
        f"string_agg(DISTINCT brand, ', ') AS brands "
        f"FROM inventory_items WHERE {ACTIVE_SLOT_WHERE} GROUP BY {key} HAVING count(*) > 1 "
        f"ORDER BY count(*) DESC, 1, 2, 3, 4"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    out = []
    for r in conn.execute(text(sql)):
        row_pos, section, level, style, color, size, pcs = r[:7]
        out.append({
            "row_pos": row_pos, "section": section, "level": level, "style": style, "color": color,
            "size": size, "pcs_per_box": pcs, "rows": r.n, "ids": list(r.ids),
            "quantities": list(r.quantities), "location": r.location, "brands": r.brands,
        })
    return out


def duplicate_summary(conn) -> tuple[int, int]:
    """(number of Part 2 duplicate groups, number of rows involved). Read-only."""
    key = ", ".join(ACTIVE_SLOT_EXPRESSIONS)
    row = conn.execute(text(
        f"SELECT count(*), coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM inventory_items "
        f"WHERE {ACTIVE_SLOT_WHERE} GROUP BY {key} HAVING count(*) > 1) d"
    )).fetchone()
    return int(row[0]), int(row[1])
