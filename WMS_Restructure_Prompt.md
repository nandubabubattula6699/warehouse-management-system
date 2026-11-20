# WMS RESTRUCTURE — instructions for the coding agent

## Context

This repository (`warehouse-management-system`) is a working warehouse management system for an apparel
wholesaler (customers: Nordstrom Rack, TJ Maxx, Cititrends, Amazon). Stack: **Python (FastAPI), PostgreSQL,
deployed on Railway, code on GitHub.** It was built quickly with AI agents, so it works but has grown
unstructured: most logic is in one large `app/main.py`, there are many lint warnings, the schema grew feature
by feature, and a recent commit removed the login requirement.

**Goal:** turn it into a properly structured, real WMS — clean modules, a sound PostgreSQL data model, migrations,
tests, and security — **without breaking what the warehouse uses today.**

## Ground rules (apply to every phase)

1. **The live system must keep working.** Restructure in small steps; every step leaves the app runnable and deployable.
2. **Never run anything against the production database** (Railway `DATABASE_URL` of the live service) unless I explicitly
   say so in that message. Use a separate dev database. Take a backup (`pg_dump`) before any production migration.
3. **All schema changes go through Alembic migrations** — no `create_all()`, no ad-hoc `ALTER TABLE` in app code.
   Every migration must be reversible (`downgrade`) and must preserve existing data.
4. **Small commits on a feature branch, one topic each**, with a clear message. Open a PR per phase; never push to `main` directly.
5. **Stop at the end of each phase**, show me a summary (what changed, test results, risks) and wait for "approved".
6. If something is unclear, ask — do not guess business rules.

---

## Phase 0 — Audit (read only: change NOTHING)

Produce `docs/AUDIT.md` containing:

1. **Inventory of the current system**: folder/file map; every API endpoint (method, path, purpose, auth required?);
   every background job/service (e.g. picking-service, vision-llm-service); external integrations; env vars used.
2. **Current database**: every table with columns, types, keys, indexes, row counts (from the dev copy), and how
   tables relate. Note tables that are unused, duplicated, or store the same fact in two places.
   Note how the schema is created today (Alembic? `create_all`? manual SQL?).
3. **Business flows as they exist today**: receiving, putaway, inventory, picking (QR picking), packing, labels,
   shipping, users/roles — describe what the code actually does.
4. **Problems ranked by risk**: security (auth removed, secrets in code, SQL injection, open endpoints), data integrity
   (missing constraints, quantities edited in place, no audit trail), reliability, maintainability.
5. **Test coverage today** and the lint/type-check status.

Also produce `docs/TARGET_ARCHITECTURE.md` with your proposal for Phases 1–6 below, adjusted to what you found,
including a **table-by-table migration map** (old table/column → new table/column, and how data is moved).

**Stop after Phase 0.**

---

## Target architecture

### Code: a modular monolith (one deployable app, clean internal modules)

```
app/
  main.py                 # app factory only: create app, include routers, middleware, lifespan
  core/                   # config (pydantic-settings), db session, security, logging, errors, pagination
  modules/
    auth/                 # users, roles, sessions/JWT, permissions
    catalog/              # customers, items/SKUs (style-color-size), UPCs/GTINs, size scales
    locations/            # warehouses, zones, aisles, bins, location types
    inventory/            # inventory ledger, balances, adjustments, cycle counts, holds
    inbound/              # ASNs/packing lists, receiving, carton scans, putaway
    outbound/             # customer orders, distribution (store/DC), allocation, waves, picking, packing
    shipping/             # cartons, labels (BarTender export), BOL, pallets, carrier info
    reporting/            # read-only queries, CSV/Excel exports
    integrations/         # EDI/GXS catalog, AI (Gemini) reading, file parsers
  each module/:
    router.py  schemas.py  models.py  service.py  repository.py  tests/
migrations/               # Alembic
tests/                    # cross-module + e2e
```

Rules: routers only handle HTTP; business rules live in `service.py` and pure functions; database access only in
`repository.py`; modules talk to each other through service functions, never by reaching into another module's tables.

### Database: core WMS data model (PostgreSQL)

Use these principles, then adapt the exact tables to what the audit found:

- **Inventory is a ledger.** Every movement (receive, putaway, move, pick, adjust, ship) inserts a row in
  `inventory_transaction`; current stock (`inventory_balance`) is updated in the same DB transaction and can always be
  rebuilt from the ledger. Quantities are never edited in place without a transaction row.
- **SKU = style + color + size.** Sizes are free text per size scale (e.g. `S R`, `14 Little Kid`, `1X`) with a sort order.
- Constraints in the database, not just in code: foreign keys, `NOT NULL`, `CHECK (qty >= 0)` where it applies,
  unique keys (e.g. one UPC per SKU), and indexes for every foreign key and common filter.
- Every table: `id` (bigint identity or uuid — pick one convention), `created_at`, `updated_at`, `created_by`;
  soft delete only where history matters.
- Money as `numeric(12,2)`, quantities as `integer`, timestamps as `timestamptz`.

Core tables (minimum):

| Area | Tables |
|---|---|
| Parties | `customer` (Nordstrom, TJX, Cititrends…), `customer_location` (stores **and** DCs, with store→DC mapping), `vendor` |
| Catalog | `style`, `color`, `size_scale`, `size`, `sku` (style+color+size), `sku_identifier` (UPC/GTIN, customer item #), `customer_sku` (customer color/size codes, e.g. NRF codes) |
| Locations | `warehouse`, `zone`, `location` (bin; type: receiving, storage, pick, staging, shipping) |
| Inventory | `inventory_balance` (sku, location, lot/PO optional, qty_on_hand, qty_allocated), `inventory_transaction` (ledger), `inventory_hold`, `cycle_count`, `cycle_count_line` |
| Inbound | `inbound_shipment` (ASN/packing list header), `inbound_carton` (expected cartons + contents), `receipt`, `receipt_line`, `carton_scan` (what was actually received, incl. photo + AI read), `putaway_task` |
| Outbound | `sales_order` (customer PO), `sales_order_line`, `order_distribution` (qty per store/DC per SKU — e.g. Nordstrom PO by store), `allocation`, `wave`, `pick_task`, `pack_carton`, `pack_carton_line` |
| Shipping | `shipment`, `pallet`, `bol`, `carton_label` (BarTender data), `tracking` |
| System | `app_user`, `role`, `permission`, `audit_log`, `job` (Postgres queue), `file_upload`, `ai_call` |

---

## Phases after the audit

1. **Safety first** — restore authentication on all endpoints (roles: worker, supervisor, admin); move secrets to env vars;
   set up dev database + Alembic baseline that matches the **current** production schema exactly (no changes yet);
   CI with ruff, mypy, pytest.
2. **Code structure** — split `main.py` into the module layout above **without changing behavior** (same URLs, same
   responses). Add tests that lock current behavior before moving code.
3. **Data model** — Alembic migrations from the old schema to the target model, with data-migration scripts and
   row-count/quantity checks before vs after. Old endpoints keep working via the new services.
4. **Inventory ledger** — all stock movements go through `inventory_transaction`; add a reconciliation check
   (balance == sum of ledger) that runs nightly.
5. **Inbound / Receiving module** — packing list import (CSV/XLSX/PDF + AI photo reading), carton scanning with photos,
   expected-vs-received, putaway tasks. (Detailed spec: `Receiving_Check_Build_Prompt.md` — build it as this module,
   using the shared catalog, locations and users, not as a separate app.)
6. **Outbound** — customer PO import (e.g. Nordstrom PO by store/DC), allocation, picking, packing sheets, carton labels
   (BarTender CSV), BOL.

Definition of done for every phase: migrations up + down tested on the dev DB, tests green in CI, no new lint
errors, app runs locally and on a Railway **staging** environment, and a short `docs/CHANGELOG.md` entry.

**Start with Phase 0 only.**
