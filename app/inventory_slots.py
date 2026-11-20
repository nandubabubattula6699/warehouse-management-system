"""
"One active row per slot" rule (migration 0003).

A slot is style + color + size + physical location (line, row, section, level, box #), normalized
exactly the way the app already matches rows when stock comes in (upper-case style/color/size,
color default STANDARD, size default OS, empty string for missing coordinates). Only ACTIVE rows
count: deactivated rows keep their history and never block a new active row.

Box # is part of the location (the app keeps separate rows per box at the same shelf, and the
displayed location includes "Box N").
"""
from sqlalchemy import text

ACTIVE_SLOT_INDEX = "uq_inventory_items_active_slot"

# Expressions of the unique index, in order (also used for the duplicate report).
ACTIVE_SLOT_EXPRESSIONS = (
    "upper(style)",
    "upper(coalesce(color, 'STANDARD'))",
    "upper(coalesce(size, 'OS'))",
    "coalesce(line, '')",
    "coalesce(row_pos, '')",
    "coalesce(section, '')",
    "coalesce(level, '')",
    "coalesce(box_num, '')",
)

ACTIVE_SLOT_CONFLICT_MESSAGE = (
    "An active row already exists for this style, color, size and location (incl. box #). "
    "Add the pieces to that row instead (Adj / sheet IN), or deactivate one of them first. Nothing was saved."
)


def find_duplicate_active_slots(conn, limit: int | None = None):
    """Read-only. Groups of ACTIVE rows that share a slot: list of dicts, biggest groups first."""
    key = ", ".join(ACTIVE_SLOT_EXPRESSIONS)
    sql = (
        f"SELECT {key}, count(*) AS n, array_agg(id ORDER BY id) AS ids, "
        f"array_agg(quantity ORDER BY id) AS quantities, min(location) AS location "
        f"FROM inventory_items WHERE is_active GROUP BY {key} HAVING count(*) > 1 "
        f"ORDER BY count(*) DESC, 1, 2, 3"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    out = []
    for r in conn.execute(text(sql)):
        style, color, size, line, row_pos, section, level, box = r[:8]
        out.append({
            "style": style, "color": color, "size": size, "line": line, "row_pos": row_pos,
            "section": section, "level": level, "box_num": box, "rows": r.n, "ids": list(r.ids),
            "quantities": list(r.quantities), "location": r.location,
        })
    return out


def duplicate_summary(conn) -> tuple[int, int]:
    """(number of duplicate groups, number of rows involved). Read-only."""
    key = ", ".join(ACTIVE_SLOT_EXPRESSIONS)
    row = conn.execute(text(
        f"SELECT count(*), coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM inventory_items "
        f"WHERE is_active GROUP BY {key} HAVING count(*) > 1) d"
    )).fetchone()
    return int(row[0]), int(row[1])
