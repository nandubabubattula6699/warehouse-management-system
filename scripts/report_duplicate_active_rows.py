"""
READ-ONLY report: active inventory rows that share the same style + color + size + location (incl. box #).
These block migration 0003 (one active row per slot). Nothing is changed.

    python scripts/report_duplicate_active_rows.py              # summary + every group
    python scripts/report_duplicate_active_rows.py out.csv      # also write one line per group to a CSV

Uses DATABASE_URL like the app. The session is opened READ ONLY.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from app.database import engine
from app.inventory_slots import duplicate_summary, find_duplicate_active_slots


def main() -> int:
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        has_flag = conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'inventory_items' AND column_name = 'is_active'"
        )).first()
        if not has_flag:
            print("inventory_items.is_active does not exist yet: run 'alembic upgrade 0002' first.")
            return 2
        groups, rows = duplicate_summary(conn)
        dups = find_duplicate_active_slots(conn)
        conn.rollback()

    print(f"{groups} slot(s) with more than one active row, {rows} rows involved.")
    for d in dups:
        print(f"{d['rows']:>3} rows  {d['style']} / {d['color']} / size {d['size']} @ {d['location']}"
              f"  ids={d['ids']}  qty={d['quantities']}")

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["style", "color", "size", "line", "row", "section", "level", "box", "location",
                        "active_rows", "total_qty", "item_ids", "quantities"])
            for d in dups:
                w.writerow([d["style"], d["color"], d["size"], d["line"], d["row_pos"], d["section"], d["level"],
                            d["box_num"], d["location"], d["rows"], sum(d["quantities"]),
                            " ".join(map(str, d["ids"])), " ".join(map(str, d["quantities"]))])
        print(f"Written: {sys.argv[1]}")
    return 1 if groups else 0


if __name__ == "__main__":
    sys.exit(main())
