# Picking Service (microservice)

QR-code floor picking for Warehouse OS. **Pilot scope:** Allbirds (Part 1) • **Line 1 • Section 1** • Levels 1–4.

One QR code is stuck on Level 1 of the section. When a worker takes pieces from **any** level of that
section, they scan it, enter the style, choose the level (and size if there are several), and press **SAVE**.
Stock is deducted right away and the pick is logged in Movements as `QR_PICK` with the worker's name.

## Architecture

```
 Phone (scan QR)
      │  https://<site>/pick/s/P1-L1-S1
      ▼
 Inventory service  (existing app, app/main.py)  ── API gateway for /pick/*  + login + inventory DB
      │  forwards /pick/*  (PICKING_SERVICE_URL)
      ▼
 Picking service    (services/picking-service)   ── QR codes, scan page, pick rules
      │  calls back:  GET  /api/auth/me                       (who is the worker)
      │               GET  /api/internal/locations/stock      (X-Internal-Key)
      │               POST /api/internal/inventory/pick       (X-Internal-Key)
      ▼
 Inventory service deducts stock + writes StockMovement in ONE transaction (row lock)
```

* The picking service has **no database access**. The inventory service stays the single owner of stock data.
* Service-to-service calls use a shared secret: `INTERNAL_API_KEY` (same value on both services).

## Endpoints (all under `/pick`)

| Path | Who | Purpose |
|---|---|---|
| `/pick/s/P1-L1-S1` | any logged-in user | Page opened by the QR code |
| `/pick/labels/P1-L1-S1` | Admin / Manager | Printable QR label (+ PNG download) |
| `/pick/qr/P1-L1-S1.png` / `.svg` | anyone | QR image |
| `/pick/api/s/P1-L1-S1` | logged-in | Station info + stock in the section |
| `POST /pick/api/s/P1-L1-S1/picks` | logged-in | `{style, level, quantity, item_id?}` |
| `/pick/health` | anyone | Health check |

## Adding more sections later

Add an entry to `PICK_STATIONS` in `app/config.py` (for example `"P1-L1-S2"`), redeploy, then print its label.

## Run locally

```bash
# terminal 1 – inventory service (repo root)
set INTERNAL_API_KEY=local-dev-key
set PICKING_SERVICE_URL=http://127.0.0.1:8001
uvicorn app.main:app --port 8000

# terminal 2 – picking service
cd services/picking-service
pip install -r requirements.txt
set INTERNAL_API_KEY=local-dev-key
set INVENTORY_SERVICE_URL=http://127.0.0.1:8000
uvicorn app.main:app --port 8001
```

Open http://localhost:8000/pick/labels/P1-L1-S1

## Railway

* New service `picking-service`, same GitHub repo, **Root Directory** = `services/picking-service` (uses its own `railway.json`). No public domain needed.
* Variables on **picking-service**: `INVENTORY_SERVICE_URL`, `INTERNAL_API_KEY`, `PUBLIC_BASE_URL=https://alexander-warehouse.up.railway.app`
* Variables on **warehouse-management-system**: `INTERNAL_API_KEY` (same value), `PICKING_SERVICE_URL=http://picking-service.railway.internal:<PORT>`
