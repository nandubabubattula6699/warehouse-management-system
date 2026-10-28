import os
import sys
import re
import time
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.database import engine, init_db, SessionLocal
from app.models import InventoryItem
from sqlalchemy.dialects.postgresql import insert

def clean_val(val):
    if pd.isna(val):
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

def migrate():
    csv_path = os.path.abspath("data/alexander_inventory.csv")
    if not os.path.exists(csv_path):
        csv_path = r"C:\Users\b7580\Downloads\ALEXANDER INVENTORY(NANDU) - ALL LOCATIONS LINE1-LINE13.csv"

    print("=" * 65)
    print("  Importing Warehouse Inventory into PostgreSQL (warehouse_db)")
    print("=" * 65)
    print(f"Reading CSV: {csv_path}")

    start_time = time.time()
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"Loaded {len(df):,} rows from CSV.")

    records = []
    for idx, row in df.iterrows():
        sku = clean_val(row["SKU"])
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
            except:
                qty = int(float(pcs_box)) if pcs_box.replace('.', '', 1).isdigit() else 0
        elif pcs_box:
            try:
                qty = int(float(pcs_box))
            except:
                qty = 0

        loc_str = format_loc(line, section, level, row_pos, box)

        pcs_int = None
        if pcs_box:
            try:
                pcs_int = int(float(pcs_box))
            except:
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

    print(f"Processed {len(records):,} clean inventory records.")

    # Initialize tables
    init_db()

    # Bulk insert in chunks of 1,000
    db = SessionLocal()
    BATCH_SIZE = 1000
    try:
        # Clear existing items if re-running
        db.query(InventoryItem).delete()
        db.commit()

        for i in range(0, len(records), BATCH_SIZE):
            chunk = records[i:i + BATCH_SIZE]
            db.bulk_insert_mappings(InventoryItem, chunk)
            db.commit()
            sys.stdout.write(f"\rProgress: {min(i + BATCH_SIZE, len(records)):,}/{len(records):,} records inserted...")
            sys.stdout.flush()

        elapsed = time.time() - start_time
        print(f"\n\n[SUCCESS] Imported {len(records):,} records into PostgreSQL in {elapsed:.2f} seconds!")
        count = db.query(InventoryItem).count()
        distinct_styles = db.query(InventoryItem.style).distinct().count()
        total_units = db.query(func.sum(InventoryItem.quantity)).scalar() or 0
        print(f"Total Rows in DB:       {count:,}")
        print(f"Total Unique Styles:    {distinct_styles:,}")
        print(f"Total Stocked Units:    {int(total_units):,}")
    except Exception as e:
        db.rollback()
        print(f"\n[Error] Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    from sqlalchemy import func
    migrate()
