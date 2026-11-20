# Changelog

## Phase 1b: foundation (branch `phase-1b-foundation`)

- **Alembic**
  - Added `alembic.ini` and `migrations/`. The DB URL comes from `app.database`, with the same rules as the app.
  - `0001` baseline: built from the local schema and identical to `warehouse_dev` (75 DDL statements). It still has to be checked against the production dump. It refuses to run on existing unstamped tables, and refuses to downgrade without `ALLOW_BASELINE_DOWNGRADE=1`.
  - `0002`: `stock_movements.item_id` FK changed to `ON DELETE RESTRICT`. Added `inventory_items.is_active` (NOT NULL, default true, indexed). Reversible.
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
  - Delete-409 messages point to Deactivate.
  - Dashboard and Manage page offer "Deactivate instead?" after a blocked delete.
  - Manage page has "Show deactivated rows" and a Reactivate button.
  - Cache-buster v34.
- **Tooling**
  - `ruff.toml` with correctness rules (E4, E7, E9, F); the code now passes it.
  - `requirements-dev.txt`; `alembic` added to `requirements.txt`.
  - `.github/workflows/ci.yml`: ruff, migration up/check/down/up on Postgres 17, and both test suites.
- **Tests**
  - The schema is built by `alembic upgrade head` (no `create_all`).
  - New `tests/test_migrations.py`: model/DB drift, round trip with data, unstamped guard, stamp path, downgrade guard, startup refusal.
  - New `tests/test_deactivate.py`.
  - 49 main-app tests and 9 picking-service tests pass.
- **Docs**
  - `docs/DEPLOY_1B.md` (production baseline check, backup, stamp, deploy, rollback).
  - `docs/schema_baseline_0001.sql`.
  - `scripts/compare_schema.py`.

## Phase 1a: emergency fixes (branch `phase-1a-emergency-fixes`)

See `DEPLOY_1A.md`.
