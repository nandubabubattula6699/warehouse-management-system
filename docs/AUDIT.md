# Phase 0 — System Audit (read-only)

**Date:** 2026-11-20 · **Commit audited:** `aceecaa` (`main`) + untracked `services/receiving-check/`
**Method:** static reading of every Python file, config, deploy file, and the frontend's API calls.
**No database was touched** (neither production nor a dev copy), so live row counts are not included. See §2.6 for
the read-only queries to run on a dev copy. Python, ruff, mypy and pytest are not installed on the audit machine, so no
tools were run. See §5.

---

## 1. Inventory of the current system

### 1.1 Folder / file map

```
warehouse-management-system/
├── app/                         Main "Warehouse OS" FastAPI app (inventory service + API gateway)
│   ├── main.py        2,058 ln  ALL endpoints, business logic, auth endpoints, internal API, gateway proxy, startup seeding
│   ├── models.py                SQLAlchemy models: 6 tables
│   ├── schemas.py               Pydantic request/response models
│   ├── database.py              Engine/session, DATABASE_URL resolution, init_db() -> create_all()
│   ├── auth.py                  PBKDF2 password hashing, session-token cookie, default user seeding, require_user/admin
│   ├── location_engine.py       Location parsing/normalising, brand/zone classification, ad-hoc ALTER TABLE, seeding
│   ├── llm_parser.py            Gemini 1.5 Flash packing-list/invoice reader + "fallback" sample-data generator
│   └── static/                  Vanilla JS/HTML frontend (index.html+app.js dashboard, manage.html+manage.js, login, inbound_client.js, auth_client.js)
├── scripts/
│   ├── migrate_inventory.py     CSV -> inventory_items loader (DELETES all inventory first); also used by auto-seed
│   └── test_db_connection.py    Connectivity check (calls init_db -> create_all)
├── data/
│   ├── alexander_inventory.csv  9,789-row seed inventory (SKU,COLOR,ROW,LINE,SECTION,LEVEL,SIZE,PCS/BOX,QTY,BOX #)
│   ├── sample_inventory.csv
│   └── Zebra_4x6_QR_..._501_Labels.pdf   1.6 MB generated artefact committed to git
├── services/
│   ├── picking-service/         QR floor picking + Zebra 4x6 label PDFs (no DB; calls main app's internal API)
│   ├── vision-llm-service/      OCR + scikit-learn token tagger for box/label photos (no DB; calls internal API)
│   │   ├── data/warehouse_catalog.json   159 KB catalog snapshot (committed)
│   │   └── models/warehouse_slm.pkl      1.4 MB pickled model (committed)
│   └── receiving-check/         UNTRACKED. Scaffolding only (Dockerfile, compose, Railway configs, requirements,
│                                pyproject). No backend/app/ code and no frontend/ folder exist yet.
├── Procfile, railway.json       Railway deploy of the main app (Railpack builder)
├── requirements.txt             Unpinned (>=) deps
├── Start_Warehouse.bat          Hard-coded path C:\Users\b7580\OneDrive\Desktop\...
└── .vscode/launch.json          References scripts/migrate_sheets.py, which does not exist
```

`README.md` also refers to `scripts/migrate_sheets.py` (missing) and says to edit `.env` (correct, but it is gitignored).

### 1.2 API endpoints — main app (`app/main.py`)

"Auth?" means the server enforces it. The frontend hides some buttons by role, but **only 4 of about 45 API routes check
anything on the server.**

| Method | Path | Purpose | Auth? |
|---|---|---|---|
| GET | `/api/health` | Liveness | No |
| GET | `/api/stats` | Counts: styles, rows, units, locations | **No** |
| GET | `/api/styles?q=&limit=` | Style list with total qty / location count | **No** |
| GET | `/api/styles-batch?styles=` | Multi-style / Line / Row lookup, physically sorted | **No** |
| GET | `/api/styles/{style_code}` | One style's rows | **No** |
| POST | `/api/items` | Create an inventory row | **No** |
| PUT | `/api/items/{id}` | Edit any field incl. style, location, qty (logs `ROW_EDIT`) | **No** |
| DELETE | `/api/items/{id}` | Delete a row, **cascade-deletes its movement history** | **No** |
| POST | `/api/items/{id}/adjust` | +/- quantity (logs movement) | **No** |
| POST | `/api/items/{id}/set-quantity` | Set an exact quantity (logs `SET_EXACT`) | **No** |
| POST | `/api/items/bulk-delete` | Delete many rows (and their history) | **No** |
| POST | `/api/styles/rename` | Rename/merge a style, **also rewrites history rows** | **No** |
| GET | `/api/movements?limit=` | Recent audit movements | **No** |
| POST | `/api/sheet-submit` | Bulk IN / OUT / SET / DELETE rows (Manager Sheet / CSV) | **No** |
| GET | `/api/location-search` | Filter rows by style/part/line/row/section/level/color | **No** |
| GET | `/api/export-csv` | Full inventory CSV download | **No** |
| GET | `/api/warehouse-overview` | Zone/line/row map summary (loads every row into memory) | **No** |
| GET | `/api/warehouse-map/aisle?part=&aisle=` | Section × level grid for one line/row | **No** |
| POST | `/api/receiving` | Single-line receive into a location (logs `RECEIVING`) | **No** |
| POST | `/api/inbound/parse-docs` | Send packing list/invoice images to Gemini (or fallback) | **No** |
| POST | `/api/inbound/shipments` | Stage a shipment for approval | **No** |
| GET | `/api/inbound/shipments` | List shipments + pending/approved counts | **No** |
| GET | `/api/inbound/shipments/{id}` | Shipment detail incl. base64 documents | **No** |
| POST | `/api/inbound/shipments/{id}/approve` | **Commit shipment to inventory** ("Admin confirmation") | **No** |
| POST | `/api/inbound/shipments/{id}/reject` | Reject a shipment | **No** |
| DELETE | `/api/inbound/shipments/{id}` | Delete a non-approved shipment | **No** |
| POST | `/api/auth/login` | Username/email + password → `wh_session` cookie (14 days) | — |
| POST | `/api/auth/signup` | Self-registration (pending approval; **caller picks own role**) | — |
| POST | `/api/auth/logout` | Clear session | Cookie |
| GET | `/api/auth/me` | Current user + online/pending counts | Cookie |
| GET | `/api/admin/users` | List users | **ADMIN** |
| POST | `/api/admin/users` | Create pre-approved user | **ADMIN** |
| POST | `/api/admin/users/{id}/status` | Approve / pending / revoke | **ADMIN** |
| DELETE | `/api/admin/users/{id}` | Delete user | **ADMIN** |
| GET | `/api/internal/locations/stock` | Section stock (for picking-service) | `X-Internal-Key` |
| POST | `/api/internal/inventory/pick` | Deduct picked qty (row-locked), log `QR_PICK` | `X-Internal-Key` |
| GET | `/api/internal/catalog` | Styles/colors/sizes catalog (for vision training) | `X-Internal-Key` |
| GET | `/api/internal/styles/lookup` | Locations for a style (for vision) | `X-Internal-Key` |
| GET/POST/PUT/DELETE | `/pick`, `/pick/{path}` | Reverse proxy → picking-service | No |
| GET/POST/PUT/DELETE | `/scan`, `/scan/{path}` | Reverse proxy → vision-llm-service | No |
| GET | `/`, `/manage`, `/login`, `/favicon.ico`, `/static/*` | HTML pages. `/` and `/manage` redirect to login if no session. `/manage` needs ADMIN/MANAGER | Page only |

### 1.3 API endpoints — picking-service (all public, login removed in `498358c`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/pick/health` | Health (`auth_required: false`) |
| GET | `/pick` | Redirect → `/pick/labels` |
| GET | `/pick/s/{code}` | Pick page opened by scanning a QR (`P1-L{line}-S{section}`) |
| GET | `/pick/labels`, `/pick/labels/{code}` | Label hub / single printable label |
| GET | `/pick/labels.pdf?line=&code=` | Zebra 4×6 PDF (all 501, one line, or one section). Cached in memory |
| GET | `/pick/qr/{code}.png` / `.svg` | QR images |
| GET | `/pick/api/stations` | All 14 lines / 501 stations |
| GET | `/pick/api/s/{code}` | Stock in that section (via internal API) |
| POST | `/pick/api/s/{code}/picks` | **Deduct stock.** `staff_name` is free text, defaults to "Floor Staff (QR Scan)". Max 500 per request |

Stations are generated from a hard-coded `LINE_SECTION_COUNTS` (Line 1 = 40 sections, … total 501). `resolve_station`
also accepts any `P1-L1..14-S1..50`, so codes outside the real layout are allowed.

### 1.4 API endpoints — vision-llm-service (all public)

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan`, `/scan/` | Scan UI |
| GET | `/scan/health` | Health + model stats |
| GET | `/scan/api/model-info` | Training report |
| POST | `/scan/api/analyze` | Image (multipart or base64) or raw text → OCR → style/color/size/qty + live locations |
| POST | `/scan/api/feedback` | Append a correction to `data/feedback.jsonl` and **retrain synchronously by default** |
| POST | `/scan/api/train` | Retrain the model (CPU-heavy, about 23 s) |

### 1.5 Background jobs / processes

- **No job queue or scheduler exists.** All work runs inside requests.
- **Startup (`lifespan` → `seed_if_empty`)** runs on every boot:
  1. `create_all()`, then ad-hoc `ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS …` (4 columns).
  2. Backfill: rewrites brand/part/placement/location_code/location for **all** rows if any row is unclassified.
  3. Seeds `warehouse_locations` (14 lines × 35 sections × 4 levels; 14 rows × (36 + FRONT/BACK/WALL) × 4; WALL aisle).
  4. **If no row has `line = '14'`, inserts the Line 14 rows from `data/alexander_inventory.csv`.**
  5. Seeds users `nandu` / `manager` with fixed passwords if missing.
  6. **If `inventory_items` is empty, runs `migrate()`, which deletes all inventory and imports the CSV.**
- **Child processes:** in the same lifespan, the main app starts picking-service (port 8001) and vision-llm-service
  (8002) with `subprocess.Popen` when `PICKING_SERVICE_URL` / `VISION_SERVICE_URL` are unset and the service's modules are
  importable. `segno` is in the main `requirements.txt`, so on Railway the picking-service probably runs **inside the main
  container** unless `PICKING_SERVICE_URL` is set. *Check this in the Railway variables.*
- **Vision model training:** at Docker build time (`python -m app.trainer`), on `/scan/api/train`, and on every
  `/scan/api/feedback` call by default. The feedback file and model live on the container's local disk and are
  **lost on redeploy**.

### 1.6 External integrations

| Integration | Where | Notes |
|---|---|---|
| Google Gemini (`gemini-1.5-flash`, REST v1beta) | `app/llm_parser.py` | API key passed in the **URL query string**. Hard-coded model name, which is probably retired by now, so calls likely fail and fall back silently |
| RapidOCR (ONNX PP-OCRv4), scikit-learn | vision-llm-service | Self-hosted; model stored with pickle |
| Railway | `railway.json`, service `railway.json`s | 3 services (main, picking, vision); Postgres plugin |
| Zebra printers | picking-service | PDF output only, no ZPL |
| Google Sheets | manual CSV export → `migrate_inventory.py` / `/manage` CSV upload | No API integration |
| EDI / GXS, BarTender, carriers | — | **Not present** |

### 1.7 Environment variables

| Var | Used by | Default in code (⚠ = risky) |
|---|---|---|
| `DATABASE_URL` / `DATABASE_PUBLIC_URL` / `POSTGRES_URL` | main | If none is set **and** `PORT`/`RAILWAY_ENVIRONMENT` is set → **SQLite file `warehouse_cloud.db`** ⚠ |
| `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD` | main (local) | `DB_PASSWORD` defaults to a real-looking password in `database.py` ⚠ |
| `INTERNAL_API_KEY` | main, picking, vision | `wh-internal-default-key-2026` hard-coded in 4 places ⚠ |
| `PICKING_SERVICE_URL`, `VISION_SERVICE_URL` | main gateway | `http://localhost:8001/8002` |
| `INVENTORY_SERVICE_URL` | picking, vision | `http://localhost:8000` |
| `PUBLIC_BASE_URL` | picking | Falls back to request `Host`/`X-Forwarded-Host` (QR URLs can be poisoned by the Host header) |
| `MAX_PICK_QUANTITY` | picking | 500 |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | main | none → sample-data fallback ⚠ |
| `MAX_IMAGE_BYTES` | vision | 12 MB |
| `PORT`, `RAILWAY_ENVIRONMENT` | main | — |
| `SERVER_HOST`, `SERVER_PORT` | `.env.example` only | **unused** |
| receiving-check: `ENV, DATABASE_URL, GEMINI_API_KEY, GEMINI_MODEL, S3_*, LOCAL_STORAGE_DIR, SESSION_SECRET, ALLOWED_ORIGINS, PHOTO_RETENTION_DAYS, MAX_UPLOAD_MB, SEED_ADMIN_*` | not yet used | Its own separate DB `receiving_check` |

---

## 2. Current database

### 2.1 How the schema is created

**No migrations.** `Base.metadata.create_all()` runs on every startup and in `test_db_connection.py`. On top of that,
`location_engine.ensure_schema_and_locations_seeded` runs **ad-hoc `ALTER TABLE … ADD COLUMN`** for `brand`,
`warehouse_part`, `placement_type`, `location_code`. `create_all` never alters existing tables, so **the production
schema may differ from `models.py`** (e.g. indexes added to models later were never created). Phase 1's Alembic
baseline must be generated by reflecting the real production schema, not from `models.py`.

All `id`s are `serial` (int4). All timestamps are `timestamp without time zone`, written with naive `datetime.utcnow()`.
No `CHECK` constraints exist anywhere.

### 2.2 Tables (from `models.py`; verify against a dev copy)

**`inventory_items`**: one row = one style + color + size + physical position (+ box #). Holds both the stock balance
and the catalog data.

| Column | Type | Null | Default / notes |
|---|---|---|---|
| id | serial PK | | |
| style | varchar(100) | NOT NULL | idx |
| brand | varchar(60) | | 'ALLBIRDS' (derived from style prefix) — idx |
| warehouse_part | varchar(30) | | 'PART_1' (derived) — idx |
| placement_type | varchar(30) | | 'RACK' (derived) — idx |
| color | varchar(100) | | 'STANDARD' — idx |
| size | varchar(50) | | 'OS' — idx |
| line | varchar(50) | | Part 1 aisle — idx |
| section | varchar(50) | | 1..40 or FRONT/BACK/WALL — idx |
| level | varchar(50) | | 1..4 — idx |
| row_pos | varchar(50) | | Part 2 aisle or WALL — idx |
| box_num | varchar(50) | | "Box #/Cartons". Used as a **carton count** in some places and a **box identifier** in others |
| location_code | varchar(120) | | `P1-L1-S1-LV1` — "links" to `warehouse_locations` but **no FK** — idx |
| location | varchar(200) | NOT NULL | 'Unassigned'. Display string derived from the coordinate columns — idx |
| pcs_per_box | integer | | |
| quantity | integer | NOT NULL | 0. **No `CHECK (quantity >= 0)`** — idx |
| created_at / updated_at | timestamp | | utcnow |

Composite indexes: `(style, location)`, `(style, size, color)`, `(warehouse_part, line, row_pos, section, level)`.
**No unique key**, so duplicate rows for the same style/color/size/position are possible and the code deals with them
with `.first()`.

**`stock_movements`**: the audit trail.

| Column | Type | Notes |
|---|---|---|
| id | serial PK | |
| item_id | int FK → inventory_items **ON DELETE CASCADE** | NOT NULL, idx |
| style | varchar(100) | Copy of the item's style, **rewritten by `/api/styles/rename`** |
| change_amount | int | NOT NULL |
| quantity_after | int | NOT NULL |
| movement_type | varchar(50) | Free text. Seen values: QUICK_ADJUST, STOCK_IN, STOCK_OUT, SET_EXACT, NEW_ENTRY, SHEET_IN, SHEET_OUT, SHEET_SET, NEW_LOCATION_IN, ROW_EDIT, RECEIVING, INBOUND_SHIPMENT_APPROVED, QR_PICK (+ anything a client sends) |
| reason | varchar(255) | |
| staff_name | varchar(100) | **Free text from the client**, not tied to a user |
| created_at | timestamp | idx |

No location, color or size is recorded: a movement only points at an item row, and that row can later be edited or
deleted.

**`warehouse_locations`**: master location list (about 2,000+ rows seeded).
Columns: `id`, `location_code` (unique), `warehouse_part`, `zone_label`, `aisle_type` (LINE/ROW/WALL), `aisle_number`,
`section`, `level`, `placement_type`, `display_location`, `created_at`. **Read by nothing except the seeding code.** No
FK from inventory. It seeds 35 sections per line, but the picking-service layout has up to 40 and the seed CSV has
Line 1 Section 40, so **the master table disagrees with the real layout.**

**`warehouse_users`**: `id`, `username` (unique), `email` (unique, nullable), `full_name`, `password_hash`
(PBKDF2-SHA256, 120k iterations), `role` (free text: ADMIN/MANAGER/PART_1_LEAD/PART_2_LEAD/STAFF), `assigned_zone` (free
text, **not enforced anywhere**), `is_approved` (int: 1/0/-1), `session_token` (**plaintext**, one per user),
`last_seen_at`, `created_at`.

**`inbound_shipments`**: `id`, `shipment_number` (unique), `po_number`, `carrier_vendor`, `pallets_count`,
`total_boxes`, `total_units`, `status` (PENDING_APPROVAL/APPROVED/REJECTED/DRAFT, free text),
`packing_list_filename`, **`packing_list_data` (Text: whole base64 image/PDF stored in the row)**,
`commercial_invoice_filename`, **`commercial_invoice_data` (Text, base64)**, `ai_extracted_raw`, `notes` (rejections
are appended to it), `created_by` / `approved_by` (free-text names), `approved_at`, `created_at`, `updated_at`.

**`inbound_shipment_items`**: `id`, `shipment_id` FK → inbound_shipments ON DELETE CASCADE, `style`, `brand`,
`warehouse_part`, `color`, `size`, `line`, `row_pos`, `section`, `level`, `box_num`, `box_count`, `pcs_per_box`,
`quantity` (received), `expected_quantity`, `location`, `notes`, `created_at`. No `placement_type` / `location_code`.
No link to the `inventory_items` row it was committed into.

### 2.3 Relationships

```
inbound_shipments 1──* inbound_shipment_items        (FK, cascade)
inventory_items   1──* stock_movements               (FK, cascade — deleting stock deletes its history)
inventory_items   ···  warehouse_locations           (location_code string only, no FK, values can mismatch)
warehouse_users   ···  everything                    (no FKs; people are recorded as free-text names)
inbound_shipment_items ··· inventory_items           (no link; matched by style/color/size/coords at approval)
```

### 2.4 Unused, duplicated, or "same fact in two places"

- **`warehouse_locations` is unused** by the app (seeded only) and out of sync with the real layout.
- **Location stored 3 times in `inventory_items`:** coordinates (`line/row_pos/section/level/box_num`) +
  `location_code` + `location` display string, plus derived `warehouse_part` / `placement_type`. Startup backfill
  rewrites them.
- **Brand derived from the style prefix** and stored per row. Changing a prefix rule silently re-classifies stock on the
  next backfill.
- **Catalog is spread across stock rows:** there is no style/SKU table. Style + color + size exist only as strings on each
  balance row. `pcs_per_box` is per balance row, not per SKU/carton.
- **`stock_movements.style`** copies `inventory_items.style`.
- **`inbound_shipments.total_boxes/total_units`** duplicate the sums of the items.
- **Users** are stored in `warehouse_users`, but every audit field (`staff_name`, `created_by`, `approved_by`) is a typed
  name.
- **Catalog snapshot** also lives in `services/vision-llm-service/data/warehouse_catalog.json` (copied out of the DB).
- **Picking layout** (`LINE_SECTION_COUNTS`) is a fourth copy of the location master, hard-coded in Python.
- **`services/receiving-check`** is set up with a **separate database** (`receiving_check`), which would create a fifth
  copy of catalog, locations and users. The restructure brief says to fold it in as a module instead.

### 2.5 Sentinel values instead of NULL

`'STANDARD'` for no color, `'OS'` for no size, `'Unassigned'` for no location. Queries use
`coalesce(x, 'STANDARD')`, so NULL and the sentinel are treated as equal in some places but not others.

### 2.6 Row counts: not collected

Per your instruction, no database was queried. On a **dev copy** (never production), these read-only queries fill the gap:

```sql
SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;
SELECT movement_type, count(*) FROM stock_movements GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) FROM inventory_items WHERE quantity < 0;                      -- should be 0
SELECT style, color, size, line, row_pos, section, level, box_num, count(*)
  FROM inventory_items GROUP BY 1,2,3,4,5,6,7,8 HAVING count(*) > 1;          -- duplicates
SELECT count(*) FROM inventory_items i LEFT JOIN warehouse_locations l USING (location_code)
  WHERE l.id IS NULL;                                                          -- orphan location codes
SELECT i.id FROM inventory_items i JOIN LATERAL (SELECT quantity_after FROM stock_movements m
  WHERE m.item_id = i.id ORDER BY created_at DESC, id DESC LIMIT 1) last ON true
  WHERE last.quantity_after <> i.quantity;                                     -- ledger drift
SELECT pg_size_pretty(pg_total_relation_size('inbound_shipments'));            -- base64 bloat
\d+ inventory_items                                                            -- real columns/indexes vs models.py
```

The local seed CSV has **9,789** inventory rows. The vision catalog snapshot has **612 styles, 126 colors, 41 sizes**.

---

## 3. Business flows as the code implements them today

**Warehouse model.** One 50,000 sq ft building in two parts. Part 1 is **Allbirds**: Lines 1–14 × Sections (34–40) ×
Levels 1–4. Part 2 is **Von Dutch / Valentino / Ed Hardy**: Rows 1–14 + WALL × Sections 1–36 + Ground FRONT/BACK +
WALL × Levels 1–4. The part and brand are inferred from the style prefix and from whether `line` or `row_pos` is filled
in. (Your brief names customers such as Nordstrom Rack, TJ Maxx, Cititrends and Amazon. **No customer concept exists in
the code.**)

**Receiving.** There are three separate paths that each add stock their own way:
1. *Quick receive*: `POST /api/receiving`. Finds the row by style/color/size/coords (+box). If found, it adds the
   quantity; if not, it creates a row. Logs `RECEIVING` with an optional PO in the reason text.
2. *Multi-pallet inbound*: upload packing list/invoice photos → `/api/inbound/parse-docs` (Gemini, or a fallback that
   **returns made-up sample lines such as A12501 / VDSW-2092 SND and a random PO number** when no key is set or the call
   fails). The manager edits the grid and assigns locations → `POST /api/inbound/shipments` (PENDING_APPROVAL) → "Admin"
   approves → every line is merged into or creates `inventory_items` and logs `INBOUND_SHIPMENT_APPROVED`. The server
   never checks that the approver is an admin.
3. *Manager Sheet / CSV*: `/api/sheet-submit` with `IN` rows.
None of these check expected vs. received (`expected_quantity` is stored but never compared), scan cartons, or check
against a catalog. New styles are created implicitly by typos.

**Putaway.** Not a separate step. The location is typed in during receiving, so stock goes straight to its final
location. There are no receiving/staging locations and no putaway tasks.

**Inventory.**
- Dashboard lookup by style / Line / Row, sorted in physical walking order; warehouse map; CSV export.
- Adjustments: +/- (`adjust`), set exact (`set-quantity`), full row edit including **moving it to another location by
  editing the coordinates** (`PUT /api/items/{id}`, logged as one `ROW_EDIT` movement with the old→new location in
  free text), delete / bulk delete (**history is deleted too**), style rename (**history is rewritten**).
- Sheet `OUT` deducts from the exact match, or else falls back to the largest matching row. `SET` overwrites.
- There are no cycle counts, holds, lots or reservations. `quantity` is edited in place. Movements are written by the
  same code but can be removed or rewritten.

**Picking (QR).** Every Part 1 section has a 4×6 QR label → phone opens `/pick/s/P1-Lx-Sy` (no login) → worker
enters style, level, size (if more than one), qty and optionally a name → picking-service → `POST
/api/internal/inventory/pick` locks the matching row (`SELECT … FOR UPDATE`), refuses to go negative, decrements and
logs `QR_PICK`. **Picks are not tied to any order.** Part 2 has no QR picking. A "Print Pick Sheet" exists on the dashboard
(client-side printing of lookup results).

**Packing / Labels / Shipping.** **Not implemented.** The only labels are the section QR labels. There are no orders,
cartons, BOLs, BarTender exports or carrier data. Stock leaves the system only through QR picks, sheet OUT rows, manual
adjustments or deletes.

**Users / roles.** Sign-up request → admin approves via `/api/admin/users/{id}/status`. Roles are ADMIN, MANAGER,
PART_1_LEAD, PART_2_LEAD and STAFF, but on the server only **ADMIN** (user management) and the **ADMIN/MANAGER**
redirect on the `/manage` HTML page mean anything. `assigned_zone` is not enforced. Two accounts (`nandu` ADMIN,
`manager` MANAGER) are recreated with fixed passwords whenever they're missing (checked on every login and signup).
The vision service has no users at all.

---

## 4. Problems ranked by risk

Severity: **Critical** = exploitable now or can silently lose or corrupt stock data; **High** = likely to cause wrong
stock or an outage; **Medium** / **Low** = maintainability and hygiene.

### 4.1 Security

| # | Sev | Finding | Where |
|---|---|---|---|
| S1 | **Critical** | **The inventory API has no authentication.** Login only gates the HTML pages. Anyone who can reach the Railway URL can read, export, adjust, set, delete, bulk-delete, rename, receive, and *approve inbound shipments* with `curl`. | `main.py` all `/api/items*`, `/api/styles*`, `/api/sheet-submit`, `/api/receiving`, `/api/inbound/*`, `/api/export-csv` |
| S2 | **Critical** | **Default credentials recreate themselves.** `ensure_default_admin` creates `nandu`/`Nandu@123` (ADMIN) and `manager`/`Manager@123` whenever missing, and runs on every login/signup. Deleting the `manager` account brings it back with the known password. The passwords are in git history. | `auth.py:31-63`, `main.py:1093,1143` |
| S3 | **Critical** | **Picking is public and can deduct stock**: `POST /pick/api/s/{code}/picks` has no auth, takes up to 500 per call, and records a typed name. Anyone with the URL (it's printed in the QR) can drain inventory. (This was a deliberate product choice in `498358c`; it needs a replacement such as a PIN or device token.) | `services/picking-service/app/main.py:206` |
| S4 | **Critical** | **Hard-coded shared secret** `wh-internal-default-key-2026` is the fallback `INTERNAL_API_KEY` in 4 files. If the env var is unset in any Railway service, internal endpoints accept the public default. | `main.py:1731`, `main.py:81`, picking `config.py:13`, vision `config.py:18` |
| S5 | High | **Stored XSS.** Style codes from the DB go into `innerHTML` and inline `onclick="addStyleToSelection('${s.style}')"` without escaping. With S1, anyone can create a style containing a script that runs in the admin's browser session. | `app/static/app.js:303,305,360` (others likely; full pass needed) |
| S6 | High | **Self-chosen role at sign-up**: `SignupPayload.role` is accepted as-is, so approving a request can grant ADMIN without the approver noticing. | `main.py:1163` |
| S7 | High | **Vision service is public**: unauthenticated `/scan/api/train` and `/scan/api/feedback` (synchronous retrain, about 23 s CPU each) allow CPU exhaustion and **training-data poisoning**. The model is loaded with `pickle`, so anyone who can write `models/` can run code. | vision `main.py:95,120` |
| S8 | High | **Real-looking password as the DB default** in `database.py` (`DB_PASSWORD` fallback), the same string as the admin password. | `database.py:29` |
| S9 | Medium | Gemini API key sent in the URL query string (can end up in proxy/HTTP logs). | `llm_parser.py:87` |
| S10 | Medium | `CORSMiddleware(allow_origins=["*"], allow_credentials=True)`: Starlette mirrors the caller's origin, so any site can make credentialed calls. Currently limited only by the cookie's `SameSite=Lax`. | `main.py:106` |
| S11 | Medium | Session tokens are stored in plaintext. There is one token per user (logging in on a second device logs out the first), no server-side expiry, and the cookie lacks `Secure`. | `auth.py`, `main.py:1121` |
| S12 | Medium | QR/PDF URLs are built from the `Host` / `X-Forwarded-Host` header when `PUBLIC_BASE_URL` is unset, so a crafted request could produce labels that point at another site (and the PDF is cached). | picking `main.py:49` |
| S13 | Low | No rate limiting on login (PBKDF2 limits speed somewhat). No brute-force lockout. | |
| — | OK | **No SQL injection found.** All queries go through the SQLAlchemy ORM with bound parameters. The f-string `ALTER TABLE` uses only constants. `_safe_next` prevents an open redirect. | |

### 4.2 Data integrity

| # | Sev | Finding |
|---|---|---|
| D1 | **Critical** | **Startup can rewrite or reload production inventory.** If `inventory_items` is ever empty (bad deploy, connection to an empty DB) the app runs `migrate()`, which **deletes all rows and imports the old CSV**. If Line 14 has no rows (for example, staff legitimately emptied it), **the old Line 14 stock is re-inserted on the next restart.** |
| D2 | **Critical** | **Silent SQLite fallback on Railway**: if `DATABASE_URL` is missing, the app starts against an empty SQLite file (then auto-seeds from the CSV, see D1). Staff would work on fake data with no error, and it would be lost on redeploy. |
| D3 | **Critical** | **Audit history can be destroyed.** `stock_movements.item_id ON DELETE CASCADE` means deleting a row or bulk-deleting deletes its history. `/api/styles/rename` rewrites `stock_movements.style`. |
| D4 | High | **AI fallback makes up shipments**: without a working Gemini key, `parse-docs` returns hard-coded sample lines and a random PO number that look like real extracted data. If someone approves without editing, phantom stock is created. |
| D5 | High | **Lost updates under concurrency**: `/api/receiving`, `/api/sheet-submit` and shipment approval read and increment `quantity` without `FOR UPDATE`. Two simultaneous receipts to the same row can lose one. (Adjust, set and internal pick do lock.) |
| D6 | High | **No uniqueness on (sku, location, box)**, so duplicate balance rows exist and `.first()` picks one arbitrarily. Sheet `OUT` falls back to "largest row anywhere in that style/color/size + optional line/section". |
| D7 | High | **No `CHECK (quantity >= 0)`** in the DB. Non-negative quantities are enforced only in some code paths (`create_item`/`POST /api/items` accepts any quantity, including negative). |
| D8 | High | **Movement ≠ ledger**: free-text `staff_name`, free-text `movement_type`, no from/to location, and a "move" is recorded as a `ROW_EDIT` on the same row. Stock by location cannot be rebuilt from history. |
| D9 | Medium | Approval doesn't check status beyond "not APPROVED", so **a REJECTED shipment can still be approved**. Lines with qty ≤ 0 are skipped silently. `expected_quantity` is never compared. |
| D10 | Medium | Multi-commit writes: `create_item` and `/api/receiving` (new row) commit the row and then the movement in a second commit. A crash between them leaves stock without history. |
| D11 | Medium | Startup backfill rewrites brand/part/location for **every** row whenever any row matches the condition, using current prefix rules (silent reclassification). |
| D12 | Medium | `box_num` means a carton count in one place (summed as `total_cartons` in sheet submit) and a box identifier in another (part of the match key). |
| D13 | Medium | Location master (`warehouse_locations`, 35 sections) doesn't match the picking layout (34–40) or the data (Line 1 Sec 40). Nothing checks that a location is real, so typos create new locations. |
| D14 | Low | Naive UTC timestamps (`timestamp without time zone`). Sentinel strings `STANDARD`/`OS`/`Unassigned` instead of NULL. |

### 4.3 Reliability / performance

| # | Sev | Finding |
|---|---|---|
| R1 | High | The schema is created by `create_all` plus ad-hoc `ALTER`. The real production schema is unknown and can drift from the models. |
| R2 | High | The web process starts other services as child processes (`subprocess.Popen`). The gateway silently falls back to `127.0.0.1`, so whether picking runs inside the main container depends on installed packages and env vars. |
| R3 | Medium | Unpinned dependencies (`>=`) in all three services, so builds aren't reproducible. |
| R4 | Medium | Base64 documents stored in `inbound_shipments` rows. Detail responses return them, and the list endpoint loads all items per shipment (N+1). |
| R5 | Medium | `/api/warehouse-overview` and the startup backfill load **every** inventory row into Python. `/api/styles-batch` builds a large OR of `LIKE 'x%'` clauses on `upper(style)` (not indexed). |
| R6 | Medium | Vision feedback/model live on ephemeral container disk (lost on redeploy). Retraining runs inside the request. The gateway proxy timeout is 120 s. |
| R7 | Medium | Gemini model name is hard-coded (`gemini-1.5-flash`, likely retired), so it probably always falls back (see D4) without anyone noticing. |
| R8 | Low | `print()` instead of logging. Startup errors are swallowed by `except Exception` in `seed_if_empty` (the app boots even if the DB is broken). Deprecated `@app.on_event` in vision. |

### 4.4 Maintainability

| # | Sev | Finding |
|---|---|---|
| M1 | High | `main.py` is 2,058 lines: routing, business rules, SQL, auth, internal API, gateway and page serving all together. The "find matching row by style/color/size/coords" query is copied 3 times. |
| M2 | Medium | Location parsing is duplicated (`_norm_*` in main and location_engine; `format_loc` in the migrate script differs from `build_location_info`). |
| M3 | Medium | Personal names and accounts are hard-coded in code paths (default staff names, "Admin (Nandu)" messages, `username == "nandu"` protection). |
| M4 | Medium | Frontend: about 90 KB `app.js` and 80 KB `index.html`, inline handlers, Tailwind/fonts from a CDN, no build or tests. |
| M5 | Low | Stale references: `migrate_sheets.py` (README, launch.json), Windows paths `C:\Users\b7580\…`, unused `SERVER_HOST/PORT`, unused imports in `main.py` (`WarehouseLocation`, `require_user`, `StyleSummary`, `SheetRowItem`, `InboundItemPayload`, `InboundItemResponse`). Generated artefacts committed (1.6 MB PDF, 1.4 MB pickle). |
| M6 | Low | `services/receiving-check/` scaffolding is untracked. Its Dockerfile copies `frontend/` and `backend/app/`, which don't exist yet, and it plans its own DB and users (conflicts with the target design). |

---

## 5. Tests, lint and type checking today

- **Tests: none.** No `tests/` folder, no pytest config, no CI (`.github/` absent). Coverage is 0%.
- **Lint / type check: not configured** in the main app (no `pyproject.toml`, ruff, flake8 or mypy config). Only the
  untracked `receiving-check/backend/pyproject.toml` defines ruff + strict mypy.
- **Could not run tools on this machine**: no Python interpreter (only the Windows Store stub), no `.venv`, no
  ruff/mypy/pytest. A static read found the unused imports listed in M5. Expect many ruff findings (line length, unused
  imports, function-local imports, `datetime.utcnow` deprecation) and many mypy findings (untyped functions, `Column`
  attribute typing). Phase 1 CI will produce the real baseline.

---

## 6. Open questions for you (business rules I won't guess)

1. **Customers vs. brands:** the code knows brands (Allbirds, Von Dutch, Valentino, Ed Hardy) but no customers. Is stock
   owned per brand/client (3PL style) or is it your own stock sold to Nordstrom Rack / TJX / Cititrends / Amazon?
2. **Box # meaning:** is `box_num` a carton count, a carton ID, or both today?
3. **QR picking without login:** what identity should a pick carry: a worker PIN, a shared device token per scanner, or
   a full login? Should picks always be against an order in the future?
4. **Part 2 picking:** should Rows/Ground/WALL also get QR stations?
5. **Real layout:** is the picking-service `LINE_SECTION_COUNTS` (501 sections) the true Part 1 layout? What's the true
   Part 2 layout?
6. **Railway:** is `PICKING_SERVICE_URL` set (separate service) or does picking run inside the main container? Is
   `INTERNAL_API_KEY` set on all three services? Is `GEMINI_API_KEY` set and is the parser actually returning real data?
7. **History:** OK to stop allowing deletion and rewriting of movement history (replace delete with "zero out + archive",
   and rename with a SKU alias)?
8. **Duplicates:** when the dev copy shows duplicate (sku, location, box) rows, should they be merged (sum quantities)?
