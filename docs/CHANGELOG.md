# Changelog

## Part 2 locations, step B (branch `feature/part2-locations`, not deployed)

- Migration `0004`: new table `locations` (Part 2 location master) and an empty, nullable `inventory_items.location_id`.
  - Codes: shelf `R<row>-S<section>-L<level>`, ground `R<row>-GF-L<level>` / `R<row>-GB-L<level>`, wall `W-SF-L<level>` /
    `W-SB-L<level>` (no section numbers), special `R-RECV` / `R-STAGE` / `R-DAMAGE`. Check constraints keep every code equal to
    its coordinates (`app/location_codes.py`); every storage spot has a level >= 1; codes unique; `created_by` required.
  - `location_id` can only be set on Part 2 rows (DB check), so Allbirds can never be linked. FK is `ON DELETE RESTRICT`.
  - Creates no locations and changes no inventory row. Downgrade refuses while any row is linked.

## Phase 1b: foundation (branch `phase-1b-foundation`)

- **Alembic**
  - Added `alembic.ini` and `migrations/`. The DB URL comes from `app.database`, with the same rules as the app.
  - `0001` baseline: built from the local schema and identical to `warehouse_dev` (75 DDL statements). It still has to be checked against the production dump. It refuses to run on existing unstamped tables, and refuses to downgrade without `ALLOW_BASELINE_DOWNGRADE=1`.
  - `0001a`: aligns an existing database with the baseline (drift found on staging, 2026-11-26). Creates the 5 missing `inventory_items` indexes (`IF NOT EXISTS`, so a no-op on a fresh DB) and drops the server defaults on `brand`/`warehouse_part`/`placement_type` (every insert path sets them explicitly). Changes no rows. Its downgrade intentionally changes nothing (0001 = the baseline).
  - `0002`: `stock_movements.item_id` FK changed to `ON DELETE RESTRICT`. Added `inventory_items.is_active` (NOT NULL, default true, indexed). Reversible.
  - `scripts/compare_schema.py` ignores the column order inside `CREATE TABLE` (columns added later by `ALTER TABLE` sit at the end).
- **No schema changes from app code**
  - Removed `init_db()`/`create_all` and the startup `ALTER TABLE ... ADD COLUMN`.
  - Startup refuses to run if the DB isn't at the head migration.
  - Location seeding (reference data, only when the table is empty) is kept.
  - Scripts check the schema instead of creating it.
- **History protection**
  - The ORM relationship no longer cascades deletes to movements (`passive_deletes="all"`).
  - The DB enforces RESTRICT.
  - `scripts/migrate_inventory.py` now fails, changing nothing, if any row has history.
- **Deactivate instead of delete**
  - `POST /api/items/{id}/deactivate|reactivate` (supervisor; deactivating requires qty 0; audited as a 0-pc movement).
  - Deactivated rows are hidden from stats, style lookups, location search (unless `include_inactive=true`), export, the warehouse map, receiving, sheet and inbound matching, and the internal picking and vision APIs.
  - Adjust, set-quantity and edit on a deactivated row return 409.
  - **Inventory rows are never hard-deleted by the app** (staging smoke test 2026-11-26: a row without history, 48 pcs, was deleted with no recorded movement). `DELETE /api/items/{id}`, `POST /api/items/bulk-delete` and the sheet `DELETE` action always return 409 and point to Deactivate (quantity 0 first, via Adj/Save, which records the stock-out).
  - The dashboard 🗑️ and Manage "Del" buttons now ask to Deactivate directly. Manage no longer offers the DELETE sheet mode/action or "Delete Checked". Cache-buster v36.
  - Dashboard and Manage page offer "Deactivate instead?" after a blocked delete.
  - Manage page has "Show deactivated rows" and a Reactivate button.
  - Cache-buster v34.
- **One active row per slot (0003): Part 2 (VD & VO, Rows) only**
  - Partial unique index on row/section/level + style + color + size + pack size (pcs per box), WHERE `is_active AND warehouse_part = 'PART_2'`. Box # is not part of the slot. The definition is in `app/inventory_slots.py`.
  - **Allbirds (Part 1, Lines) is not covered and not changed.** It keeps one row per carton, exactly as before. No migration changes any data (a test checks per-Line row count, total pcs, boxes, every row and its history).
  - The migration refuses, changing nothing, if Part 2 has duplicates. `scripts/report_duplicate_active_rows.py` (read-only) lists them.
  - warehouse_dev has 5 Part 2 duplicate groups (11 rows), so 0003 is blocked there. See DEPLOY_1B.
  - Part 2 constraint violations return 409 with a clear message. Sheet rows for the same new Part 2 slot merge into one row; on Lines they still create one row per carton.
  - `alembic upgrade` now runs all pending migrations in a single transaction.
- **Audit export:** `GET /api/export-csv?include_inactive=true` (ADMIN only) adds deactivated rows and an ACTIVE column. Manage page has an admin-only button for it. Cache-buster v35.
- **Tooling**
  - `ruff.toml` with correctness rules (E4, E7, E9, F); the code now passes it.
  - `requirements-dev.txt`; `alembic` added to `requirements.txt`.
  - `.github/workflows/ci.yml`: ruff, migration up/check/down/up on Postgres 17, and both test suites.
- **Tests**
  - The schema is built by `alembic upgrade head` (no `create_all`).
  - New `tests/test_migrations.py`: model/DB drift, round trip with data, unstamped guard, stamp path, downgrade guard, startup refusal.
  - New `tests/test_deactivate.py`.
  - New `tests/test_active_slots.py`.
  - 65 main-app tests and 9 picking-service tests pass.
- **Docs**
  - `docs/DEPLOY_1B.md` (production baseline check, backup, stamp, deploy, rollback).
  - `docs/schema_baseline_0001.sql`.
  - `scripts/compare_schema.py`.

## Phase 1a: emergency fixes (branch `phase-1a-emergency-fixes`)

See `DEPLOY_1A.md`.
