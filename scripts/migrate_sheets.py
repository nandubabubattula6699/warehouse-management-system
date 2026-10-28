import os
import sys
import time
import argparse
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.database import engine, init_db, SessionLocal
from app.models import Product, StockMovement
from sqlalchemy.dialects.postgresql import insert

COLUMN_MAPPINGS = {
    "sku": ["sku", "item code", "product code", "code", "id", "part_number", "part number", "barcode"],
    "name": ["name", "product name", "item name", "title", "description", "item"],
    "location": ["location", "address", "shelf", "bin", "rack", "aisle", "storage location", "bin location", "wh_address"],
    "quantity": ["quantity", "qty", "stock", "count", "units", "on hand", "inventory"],
    "min_quantity": ["min_quantity", "min qty", "reorder level", "safety stock", "threshold"],
    "category": ["category", "dept", "department", "type", "group"],
    "unit_price": ["price", "unit price", "cost", "unit cost", "rate"]
}

def detect_column(df, candidates):
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate in cols_lower:
            return cols_lower[candidate]
    return None

def migrate_file(filepath):
    print("=" * 65)
    print("  Google Sheets / CSV Migration Tool (20,000+ Items)")
    print("=" * 65)
    print(f"Reading: {filepath}")

    if not os.path.exists(filepath):
        print(f"[Error] File not found: {filepath}")
        return

    start_time = time.time()

    if filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath, low_memory=False)

    total_rows = len(df)
    print(f"Detected {total_rows:,} rows in spreadsheet.")

    mapped = {}
    for target_field, candidates in COLUMN_MAPPINGS.items():
        found = detect_column(df, candidates)
        if found:
            mapped[target_field] = found
            print(f"  Mapped '{found}' -> {target_field}")
        else:
            print(f"  Notice: No match for '{target_field}', using defaults.")

    if "sku" not in mapped and "name" not in mapped:
        print("[Error] Spreadsheet must have at least an SKU or Product Name column.")
        return

    clean_df = pd.DataFrame()

    if "sku" in mapped:
        clean_df["sku"] = df[mapped["sku"]].astype(str).str.strip()
    else:
        clean_df["sku"] = [f"SKU-{i+1:06d}" for i in range(total_rows)]

    if "name" in mapped:
        clean_df["name"] = df[mapped["name"]].fillna("Unnamed Item").astype(str).str.strip()
    else:
        clean_df["name"] = clean_df["sku"]

    if "location" in mapped:
        clean_df["location"] = df[mapped["location"]].fillna("Unassigned").astype(str).str.strip()
    else:
        clean_df["location"] = "Aisle 1 - General"

    if "quantity" in mapped:
        clean_df["quantity"] = pd.to_numeric(df[mapped["quantity"]], errors="coerce").fillna(0).astype(int)
    else:
        clean_df["quantity"] = 0

    if "min_quantity" in mapped:
        clean_df["min_quantity"] = pd.to_numeric(df[mapped["min_quantity"]], errors="coerce").fillna(5).astype(int)
    else:
        clean_df["min_quantity"] = 5

    if "category" in mapped:
        clean_df["category"] = df[mapped["category"]].fillna("General").astype(str).str.strip()
    else:
        clean_df["category"] = "General"

    if "unit_price" in mapped:
        clean_df["unit_price"] = pd.to_numeric(df[mapped["unit_price"]], errors="coerce").fillna(0.0).astype(float)
    else:
        clean_df["unit_price"] = 0.0

    clean_df = clean_df.drop_duplicates(subset=["sku"])
    clean_records = clean_df.to_dict(orient="records")

    print(f"Ready to import {len(clean_records):,} unique products into PostgreSQL...")

    init_db()

    BATCH_SIZE = 1000
    db = SessionLocal()

    try:
        for i in range(0, len(clean_records), BATCH_SIZE):
            chunk = clean_records[i:i + BATCH_SIZE]
            stmt = insert(Product).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sku"],
                set_={
                    "name": stmt.excluded.name,
                    "location": stmt.excluded.location,
                    "quantity": stmt.excluded.quantity,
                    "min_quantity": stmt.excluded.min_quantity,
                    "category": stmt.excluded.category,
                    "unit_price": stmt.excluded.unit_price,
                }
            )
            db.execute(stmt)
            db.commit()
            sys.stdout.write(f"\rProgress: {min(i + BATCH_SIZE, len(clean_records)):,}/{len(clean_records):,} products processed...")
            sys.stdout.flush()

        elapsed = time.time() - start_time
        print(f"\n\n[SUCCESS] Migration finished in {elapsed:.2f} seconds!")
        print(f"Total rows in PostgreSQL products table: {db.query(Product).count():,}")

    except Exception as e:
        db.rollback()
        print(f"\n[Error] Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Google Sheets / CSV into PostgreSQL Warehouse DB")
    parser.add_argument("file", nargs="?", default="data/sample_inventory.csv", help="Path to CSV or Excel file")
    args = parser.parse_args()

    target = os.path.abspath(args.file)
    migrate_file(target)
