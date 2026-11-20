# Target Architecture & Phase Plan (proposal — needs your approval)

Based on `docs/AUDIT.md`. Finding IDs (S1, D3, …) refer to that file. Nothing here has been implemented.

## 0. Key decisions proposed

| Topic | Proposal | Why |
|---|---|---|
| Deployable units | **One modular monolith** (`app/`) for all business logic and data. Picking and vision UIs become modules (`outbound/picking`, `integrations/vision`). The OCR model may stay a **separate stateless service** because of its heavy deps (OpenCV/ONNX). It gets no DB access and sits behind auth | Ends the 3–4 copies of catalog/layout/users (audit §2.4), removes the `subprocess.Popen` gateway (R2) |
| receiving-check | Do **not** build it as a separate app with its own DB. Its plan (Alembic, async SQLAlchemy, argon2, S3 photos, Postgres job queue, ruff + strict mypy) becomes the `inbound` module and the shared `core` | Brief requirement; avoids a fifth copy of the master data |
| IDs | `bigint generated always as identity` everywhere. Existing int ids are kept (widened) so URLs and the frontend keep working | Simplest, keeps current ids |
| Sync vs async | Stay **sync SQLAlchemy 2.0** in Phase 2 (behavior lock). Revisit async later only if needed | Fewer moving parts during the split |
| Auth | Server-side sessions (hashed token, expiry, multiple per user) + roles **worker / supervisor / admin** + permissions. QR picking uses a **per-worker PIN or a per-device token**, not the full login (your call, AUDIT §6 Q3) | Restores S1/S3 without slowing the floor |
| Time | `timestamptz`, UTC, created by the DB (`now()`) | D14 |
| Files | Packing lists and photos go to object storage (Railway volume or S3-compatible). The DB keeps `file_upload` rows | R4 |

## 1. Code layout

As in the brief, with the adjustments in **bold**:

```
app/
  main.py               app factory: routers, middleware, lifespan (NO seeding, NO subprocesses, NO create_all)
  core/                 settings (pydantic-settings, required vars fail fast), db, security, logging, errors, pagination
  modules/
    auth/               users, roles, permissions, sessions, **worker PINs / device tokens for QR**
    catalog/            customer, vendor, **brand**, style, color, size_scale, size, sku, sku_identifier, customer_sku
    locations/          warehouse, zone, location (**generated from a layout definition = single source for map + QR labels**)
    inventory/          ledger, balances, adjustments, moves, cycle counts, holds, reconciliation
    inbound/            ASN/packing list import, receipts, carton scans + photos, putaway (absorbs receiving-check plan)
    outbound/           orders, distribution, allocation, waves, **picking (QR station pages + pick tasks)**, packing
    shipping/           shipment, pallet, BOL, carton labels (BarTender CSV), **QR section label PDFs**
    reporting/          read-only queries, CSV/Excel exports, **warehouse map/overview (SQL aggregates)**
    integrations/       Gemini document reader, **vision-service client**, file parsers
  static/               existing frontend, unchanged URLs (later: escape all output, S5)
migrations/             Alembic
tests/
services/vision-ocr/    optional stateless OCR service (auth via service token, no DB, model in object storage)
```

## 2. Phases, adjusted to what the audit found

### Phase 1 — Safety first (no schema change, no behavior change for legitimate users)
1. **Stop startup from touching data** (D1, D2): remove the auto-`migrate()`, the Line 14 re-seed, the backfill and the
   ad-hoc `ALTER` from startup. Fail fast if `DATABASE_URL` is missing (no SQLite fallback). Seeding becomes an
   explicit CLI command for dev only.
2. **Auth on every `/api/*` route** (S1), using the existing session cookie. The frontend already sends it, so the
   pages keep working. Role map: ADMIN → admin, MANAGER / PART_*_LEAD → supervisor, STAFF → worker. Destructive
   endpoints (delete, bulk-delete, rename, approve, sheet-submit, set-quantity, PUT item) require supervisor+. Approval
   requires admin.
3. **Default accounts** (S2): seed only from env vars, only when the users table is empty, and never recreate
   afterwards. Rotate the `nandu` / `manager` passwords in production (your action).
4. **Secrets** (S4, S8, S9): remove all hard-coded fallbacks. Require `INTERNAL_API_KEY`. Gemini key goes in a header.
5. **QR picking** (S3): add the identity mechanism you choose (PIN or device token) **with a transition flag**, so
   floor picking isn't blocked on deploy day.
6. **Quick fixes**: signup role is forced to worker (S6), CORS limited to the app's origin (S10), cookie `Secure` (S11),
   `PUBLIC_BASE_URL` required for QR (S12), vision train/feedback admin-only (S7), escape the known XSS sinks (S5).
   The parse-docs fallback returns **empty** results clearly labeled "AI unavailable" instead of sample data (D4).
7. **Dev DB + Alembic baseline**: restore a `pg_dump` of production into a dev DB, reflect the **actual** schema
   (`alembic revision` written by hand from `\d+` output, not autogenerated from `models.py`, R1), and mark production
   with `alembic stamp` (no DDL). Confirm `upgrade` and `downgrade` give an identical schema on dev.
8. **CI**: GitHub Actions running ruff, mypy (non-strict first, using a baseline file), and pytest against a Postgres
   service container. Pin dependencies (R3).

### Phase 2 — Code structure (same URLs, same JSON)
1. Write **characterization tests** first: one test per endpoint in audit §1.2–1.4, recording the current response
   shape (snapshot tests), including error messages the frontend shows.
2. Move code into `modules/*` (router → service → repository). Deduplicate the "find matching row" query (3 copies) and
   the location normalizers into `locations.service`.
3. Merge picking-service into `outbound/picking` (same `/pick/*` paths) and remove the gateway proxy for it. Vision:
   keep the `/scan/*` UI in the monolith; call the OCR service through `integrations/vision` with a service token.
4. Replace `print` with structured logging. Remove dead code and stale scripts (M5).

### Phase 3 — Data model (expand → migrate → contract, all reversible)
Each step is its own Alembic revision. The old tables stay until the new ones are verified, and old endpoints are
re-implemented on the new services (see §3 migration map).
1. **Expand**: create the new tables alongside the old ones.
2. **Backfill** with data-migration scripts. Before/after checks: row counts, `sum(quantity)` per style/color/size,
   per location, and grand total must match exactly. Duplicates and orphans found in the audit queries are resolved by the
   rules you approve (AUDIT §6 Q8).
3. **Switch reads/writes** to the new tables behind the existing endpoints.
4. **Contract** (only after a period running in production with you signing off): drop the old tables. The downgrade
   rebuilds them from the new tables.

### Phase 4 — Inventory ledger
All movements go through `inventory.service.post_transaction()`: insert a ledger row and update the balance in the
same DB transaction, with `SELECT … FOR UPDATE` on the balance (fixes D5). Deletes become zero-out transactions;
renames become SKU aliases (D3). A nightly reconciliation job (`job` table, Postgres queue with
`FOR UPDATE SKIP LOCKED`) checks `balance = Σ ledger` and flags differences.

### Phase 5 — Inbound / Receiving module
Build the receiving-check spec as `modules/inbound`: packing list import (CSV/XLSX/PDF + Gemini reading, configurable
model), carton scanning with photos (object storage), expected vs. received, receipts into a **RECEIVING** location,
then putaway tasks to storage locations (ledger `RECEIVE` then `PUTAWAY`). Replaces `/api/receiving`,
`/api/inbound/*` and sheet `IN` (old URLs kept as adapters until the frontend switches).

### Phase 6 — Outbound
Customer PO import (Nordstrom by store/DC, etc.), distribution, allocation (`qty_allocated`), waves, pick tasks (QR
pick pages now confirm **pick tasks**; free picks stay as an "unplanned pick" adjustment type), pack cartons, BarTender
CSV labels, BOL, shipment.

## 3. Table-by-table migration map

Legend: **→** column moves, **⇒** derived/transformed, **✗** dropped (kept until contract step).

### 3.1 `inventory_items` (split into catalog + location + balance)

| Old | New | How |
|---|---|---|
| `style` | `style.code` | `DISTINCT upper(trim(style))`. Spaces kept (`VDSW-2092 SND`). Near-duplicates (e.g. `11159` vs `A11159`) listed for your review, not auto-merged |
| `brand` | `brand.name` + `style.brand_id` | Distinct values → `brand`. Per style, use the most common brand among its rows. Conflicts listed |
| `color` | `color.code` + `sku.color_id` | `'STANDARD'` → one color row "STANDARD" (kept, since the frontend shows it) |
| `size` | `size.label` + `size_scale` + `sku.size_id` | `'OS'` → scale "ONE SIZE". Numeric shoe sizes → scale "US SHOE" (sort = numeric). S/M/L/XL → "ALPHA" (sort from the existing `_SIZE_ORDER_MAP`) |
| (style, color, size) | `sku` | One row per distinct triple. Unique `(style_id, color_id, size_id)` |
| `warehouse_part` | `zone` (`PART_1`, `PART_2`) | ⇒ |
| `line` / `row_pos` / `section` / `level` / `placement_type` | `location` (`aisle`, `section`, `level`, `location_type`) | Matched on the normalized coords. Missing ones are created and flagged `is_verified = false` for review. `placement_type` → `location_type` (RACK→storage, GROUND_FRONT/BACK→floor, WALL→wall) |
| `location_code` | `location.code` | Recomputed by one function. Old value ✗ |
| `location` (display) | ✗ | Built in the view or API from `location` |
| `box_num` | `inventory_balance.lpn` (carton/box id) **or** `inventory_balance.carton_count` | Depends on your answer to AUDIT §6 Q2 |
| `pcs_per_box` | `sku_pack.pcs_per_carton` (default per SKU) + `inventory_balance.pcs_per_carton` (override) | Most common value per SKU becomes the default |
| `quantity` | `inventory_balance.qty_on_hand` | Duplicate (sku, location, box) rows are **summed** (if approved). Then `CHECK (qty_on_hand >= 0)` and `UNIQUE (sku_id, location_id, lpn)` |
| `id` | `inventory_balance.legacy_item_id` | Kept so old `/api/items/{id}` URLs and existing movements resolve |
| `created_at` / `updated_at` | same, `timestamptz` | Interpreted as UTC |
| — | `inventory_transaction` opening row | One `OPENING_BALANCE` transaction per balance equal to the migrated qty, so `Σ ledger = balance` from day one |

### 3.2 `stock_movements` → `inventory_transaction`

| Old | New | How |
|---|---|---|
| `id` | `legacy_movement_id` | |
| `item_id` | `sku_id` + `location_id` (from the item's **current** row) | Item already deleted → movement is gone (it cascaded). Rows exist only for surviving items |
| `change_amount` | `qty` (signed) | |
| `quantity_after` | `qty_after` (informational) | |
| `movement_type` | `txn_type` (enum) | Map: STOCK_IN/QUICK_ADJUST(+)/SET_EXACT/SHEET_SET/ROW_EDIT → `ADJUST`; RECEIVING/INBOUND_SHIPMENT_APPROVED/SHEET_IN/NEW_ENTRY/NEW_LOCATION_IN → `RECEIVE`; QR_PICK → `PICK`; STOCK_OUT/SHEET_OUT → `ISSUE`; unknown → `LEGACY` |
| `reason` | `reason` | |
| `staff_name` | `created_by_name` (text) + `created_by` (user FK, null for history) | Matched to a user only when the name equals a `full_name` exactly |
| `style` | ✗ (comes from the SKU) | |
| `created_at` | `created_at timestamptz` | |
| | **Note:** historic transactions are **not** used for the opening balance (they're incomplete because of D3). They're imported as `is_historical = true` and excluded from reconciliation. | |

### 3.3 `warehouse_locations` → `warehouse` / `zone` / `location`

| Old | New | How |
|---|---|---|
| `location_code` | `location.code` | |
| `warehouse_part`, `zone_label` | `zone.code`, `zone.name` | |
| `aisle_type`, `aisle_number`, `section`, `level` | `location.aisle_type`, `aisle`, `section`, `level` | |
| `placement_type` | `location.location_type` | as above |
| `display_location` | ✗ (computed) | |
| Hard-coded `LINE_SECTION_COUNTS` (picking) | `location` rows | The layout definition becomes the **single source**. Sections 36–40 that are missing get added. QR stations = distinct (aisle, section) in PART_1 (later PART_2) |
| — | new `RECEIVING`, `STAGING`, `SHIPPING` locations | For Phase 5/6 flows |

### 3.4 `warehouse_users` → `app_user`, `role`, `user_role`, `session`

| Old | New | How |
|---|---|---|
| `id`, `username`, `email`, `full_name` | same | |
| `password_hash` (PBKDF2) | `password_hash` | Kept. Re-hashed to argon2 the next time the user logs in |
| `role` | `user_role` → `role` | ADMIN→admin, MANAGER/PART_*_LEAD→supervisor, STAFF→worker |
| `assigned_zone` | `user_zone` (optional) | Only if you want zone restrictions enforced |
| `is_approved` (1/0/-1) | `status` enum (`active`, `pending`, `revoked`) | |
| `session_token` | `session` table (hashed token, expiry, user agent) | Existing sessions invalidated (everyone logs in once) |
| `last_seen_at`, `created_at` | same, `timestamptz` | |

### 3.5 `inbound_shipments` / `inbound_shipment_items` → inbound module

| Old | New | How |
|---|---|---|
| `inbound_shipments` row | `inbound_shipment` | `shipment_number`, `po_number`, `pallets_count`, `status` (enum), `created_at` → same |
| `carrier_vendor` | `vendor` (+ `inbound_shipment.vendor_id`) | Distinct names → vendor rows |
| `packing_list_data` / `commercial_invoice_data` (base64) | `file_upload` rows + object storage | Decoded and uploaded. Columns ✗ after verification (big DB size reduction) |
| `ai_extracted_raw` | `ai_call` row (`purpose = packing_list_parse`) | |
| `notes` (with appended rejections) | `notes` + `audit_log` entries for approve/reject | Rejection text kept as is in `notes` |
| `created_by` / `approved_by` (names) | `created_by` / `approved_by` user FKs + `*_name` text for history | |
| `total_boxes` / `total_units` | ✗ (computed) | |
| APPROVED shipments | + `receipt` row | Linked to the `RECEIVE` transactions created at approval where they can be matched (time + style + qty). Otherwise reason-only |
| `inbound_shipment_items` | `inbound_carton` (expected) + `receipt_line` (received) | `expected_quantity` → expected; `quantity` → received; style/color/size → `sku_id`; coords → `location_id` (putaway target) |

### 3.6 New tables with no old source
`customer`, `customer_location`, `sku_identifier`, `customer_sku`, `inventory_hold`, `cycle_count(_line)`, `carton_scan`,
`putaway_task`, all outbound and shipping tables, `permission`, `audit_log`, `job`, `ai_call`, `file_upload`.

## 4. Risks and how each phase limits them

| Risk | Mitigation |
|---|---|
| Phase 1 auth breaks floor work | Frontend already sends the cookie. QR picking gets a transition flag. Deploy to staging first and walk through every page |
| Baseline doesn't match production | Hand-written baseline from `\d+` of a production dump, run on dev, `stamp` only on production, `pg_dump` before any production DDL |
| Quantity drift during data migration | Exact `sum(quantity)` checks per SKU/location; migration aborts on any mismatch |
| Losing history | Old tables kept read-only until contract. Contract only with your explicit approval |
| Downtime | Expand/contract migrations are online. Data backfill done in batches |
