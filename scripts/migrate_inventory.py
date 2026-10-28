import csv
import os
import re
import sys
import time
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv()

from app.database import init_db, SessionLocal
from app.models import InventoryItem

def clean_val(val):
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    if s.endswith(".0"):
        s = s[:-2]
    return s

def format_loc(line, section, level, row, box):
    parts = []
    if line: parts.append(f"Line {line}")
    if section: parts.append(f"Sec {section}")
    if level: parts.append(f"Lvl {level}")
    if row: parts.append(f"Row {row}")
    if box: parts.append(f"Box {box}")
    return " • ".join(parts) if parts else "Unassigned"

def load_csv_records(csv_path):
    records = []
    with open(csv_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = clean_val(row.get("SKU"))
            if not sku:
                continue
            color = clean_val(row.get("COLOR")) or "STANDARD"
            line = clean_val(row.get("LINE"))
            section = clean_val(row.get("SECTION"))
            level = clean_val(row.get("LEVEL"))
            row_pos = clean_val(row.get("ROW"))
            box = clean_val(row.get("BOX #"))
            size = clean_val(row.get("SIZE")) or "OS"
            pcs_box = clean_val(row.get("PCS/BOX"))
            qty_val = clean_val(row.get("QTY"))

            qty = 0
            if qty_val:
                nums = re.findall(r"\d+", qty_val)
                qty = int(nums[0]) if nums else 0
            elif pcs_box and box:
                try:
                    qty = int(float(pcs_box)) * int(float(box))
                except Exception:
                    qty = int(float(pcs_box)) if pcs_box.replace(".", "", 1).isdigit() else 0
            elif pcs_box:
                try:
                    qty = int(float(pcs_box))
                except Exception:
                    qty = 0

            loc_str = format_loc(line, section, level, row_pos, box)

            pcs_int = None
            if pcs_box:
                try:
                    pcs_int = int(float(pcs_box))
                except Exception:
                    pass

            records.append({
                "style": sku,
                "color": color,
                "size": size,
                "line": line,
                "section": section,
                "level": level,
                "row_pos": row_pos,
                "box_num": box,
                "location": loc_str,
                "pcs_per_box": pcs_int,
                "quantity": qty
            })
    return records

def migrate(target_session_factory=None):
    csv_path = os.path.join(PROJECT_ROOT, "data", "alexander_inventory.csv")
    if not os.path.exists(csv_path):
        csv_path = r"C:\Users\b7580\Downloads\ALEXANDER INVENTORY(NANDU) - ALL LOCATIONS LINE1-LINE13.csv"

    print(f"Reading CSV: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"[Error] CSV file not found: {csv_path}")
        return

    start_time = time.time()
    records = load_csv_records(csv_path)
    print(f"Loaded {len(records):,} valid inventory rows from CSV.")

    if target_session_factory is None:
        init_db()
        db = SessionLocal()
    else:
        db = target_session_factory()

    BATCH_SIZE = 1000
    try:
        db.query(InventoryItem).delete()
        db.commit()
        for i in range(0, len(records), BATCH_SIZE):
            chunk = records[i:i + BATCH_SIZE]
            db.bulk_insert_mappings(InventoryItem, chunk)
            db.commit()
        elapsed = time.time() - start_time
        print(f"[SUCCESS] Imported {len(records):,} records in {elapsed:.2f}s!")
    except Exception as e:
        db.rollback()
        print(f"[Error] Migration failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
