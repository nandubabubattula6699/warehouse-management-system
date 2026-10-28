# Warehouse OS - Inventory Management System
High-performance Python & PostgreSQL Warehouse Management System designed to handle 20,000+ items with instant warehouse location address lookups and 1-click staff quantity adjustments.

---

## Quick Start (3 Steps)

### 1. Set Up Python Virtual Environment
Open your terminal inside this folder:
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

### 2. Configure Your PostgreSQL Password
Open the `.env` file in this directory and update your password:
```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=warehouse_db
DB_USER=postgres
DB_PASSWORD=your_actual_password_here
```

Test your database connection:
```bash
python scripts/test_db_connection.py
```
*(The script will automatically create warehouse_db and tables for you!)*

### 3. Start the Warehouse Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open your browser at: http://localhost:8000

---

## Migrating 20,000+ Rows from Google Sheets

1. In Google Sheets, download your sheet: File -> Download -> Comma Separated Values (.csv)
2. Save the file into `data/my_sheet.csv`
3. Run the high-speed migration script:
```bash
python scripts/migrate_sheets.py data/my_sheet.csv
```
*(To test with sample data right away, run `python scripts/migrate_sheets.py data/sample_inventory.csv`)*

---

## Features for Warehouse Staff
- Prominent Location Addresses: Immediate visibility of Aisle, Rack, Shelf, and Bin numbers.
- 1-Click Adjustments: Quick + and - buttons in the table for immediate stock changes.
- Audit History: Every quantity change is logged with timestamp, reason, and staff name.
- Instant Search: Sub-millisecond indexed lookup by SKU, product name, or location.
