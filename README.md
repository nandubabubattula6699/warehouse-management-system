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

### 2. Configure Your PostgreSQL Connection
Copy `.env.example` to `.env` and set `DATABASE_URL` (the app refuses to start without it):
```ini
DATABASE_URL=postgresql://postgres:your_actual_password_here@localhost:5432/warehouse_db
```

Test your database connection:
```bash
python scripts/test_db_connection.py
```
*(The script creates the tables if they are missing. The app never loads or changes inventory on startup.)*

### 3. Start the Warehouse Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open your browser at: http://localhost:8000

---

## Migrating 20,000+ Rows from Google Sheets

1. In Google Sheets, download your sheet: File -> Download -> Comma Separated Values (.csv)
2. Save the file as `data/alexander_inventory.csv`
3. **DESTRUCTIVE — deletes ALL existing inventory rows first.** Only for an empty/dev database:
```bash
python scripts/migrate_inventory.py --i-understand-this-deletes-all-inventory
```
For day-to-day changes use the CSV upload on the `/manage` page instead.

---

## Features for Warehouse Staff
- Prominent Location Addresses: Immediate visibility of Aisle, Rack, Shelf, and Bin numbers.
- 1-Click Adjustments: Quick + and - buttons in the table for immediate stock changes.
- Audit History: Every quantity change is logged with timestamp, reason, and staff name.
- Instant Search: Sub-millisecond indexed lookup by SKU, product name, or location.
