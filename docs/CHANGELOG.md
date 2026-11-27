# Changelog

## Part 2 locations, step B (branch `feature/part2-locations`, not deployed)

- Migration `0004`: new table `locations` (Part 2 location master) and an empty, nullable `inventory_items.location_id`.
  - Codes: shelf `R<row>-S<section>-L<level>`, ground `R<row>-GF-L<level>` / `R<row>-GB-L<level>`, wall `W-SF-L<level>` /
    `W-SB-L<level>` (no section numbers), special `R-RECV` / `R-STAGE` / `R-DAMAGE`. Check constraints keep every code equal to
    its coordinates (`app/location_codes.py`); every storage spot has a level >= 1; codes unique; `created_by` required.
  - `location_id` can only be set on Part 2 rows (DB check), so Allbirds can never be linked. FK is `ON DELETE RESTRICT`.
  - Creates no locations and changes no inventory row. Downgrade refuses while any row is linked.
  - `location_changes`: append-only record (DB trigger refuses UPDATE / DELETE / TRUNCATE) of every create / deactivate /
    reactivate, with who, when and the source file.

## Part 2 locations, steps D0-D3 (same branch, not deployed)

- D0 (`/locations` step 4, admin): deactivate active Part 2 rows at qty 0, preview first. Rows at spots that no longer
  exist are always included; rows at 0 at spots that still exist (e.g. "to be counted") only when ticked. Each row gets a
  recorded `DEACTIVATE` movement. Rows with stock and Allbirds rows are never included.
- D1/D2 (`/locations` step 5, admin): match report (also as CSV) of active Part 2 rows to active locations; apply links
  exactly the report: `location_id` set, a recorded 0-pc `LOCATION_LINK` movement per row. Refused while any row with stock
  has no spot (or is linked elsewhere), or when the report is stale (409). No quantity changes.
- D2 undo (`/locations` step 6, admin): unlink a whole D2 link run (default: the last one) or every row at one location
  code; preview first. Each row gets a recorded 0-pc `LOCATION_UNLINK` movement; quantities never change. A run undo skips
  rows edited or moved since that run (listed). Each D2 run now writes its run id into the `LOCATION_LINK` reasons
  ("Linked to location R4-S21-L1 [link run 3f2a9c1b7d10]"). API: `GET /api/locations/unlink/runs`, `GET .../unlink/preview`,
  `POST .../unlink/apply`.
- D3: Part 2 create, edit, sheet IN/SET, receiving, inbound approval and reactivate resolve the spot and set
  `location_id`. With `PART2_LOCATIONS_ENFORCED=1` a spot that is not an active location is refused with a 409 naming the
  spot (a sheet is not saved at all). Off by default until D2 is done. Allbirds is never checked or linked.
- API (ADMIN only): `GET /api/locations/empty-rows/preview`, `POST .../empty-rows/apply`, `GET /api/locations/link/preview`,
  `GET .../link/report.csv`, `POST .../link/apply`.
- Deploy steps: `docs/DEPLOY_PART2_LOCATIONS.md` (staging sets `LOCATION_LABEL_BASE_URL` to the staging address).

## Part 2 locations, step E (same branch, not deployed)

- Zebra label PDF, one label per page: `GET /api/locations/labels.pdf?code=R3-S5-L2` | `?row=3` (or `WALL`, `SPECIAL`) |
  `?all=true`; active spots only; ADMIN or MANAGER. Print buttons on `/locations`.
- Label (default 4x6 portrait, same roll as Allbirds): the code large on top, the description and "PART 2", a line, a large
  QR (link ending with the code) with "QR: phone camera", and at the bottom a Code 128 barcode of the code only with the
  code and "Barcode: scanner gun" under it. Bars are whole 203-dpi printer dots with quiet zones. `4x2` gives a compact
  landscape layout (QR left, code + barcode right).
- Settings (env): `LOCATION_LABEL_SIZE` (default `4x6`), `LOCATION_LABEL_QR` (default `{base}/loc/{code}`; `{code}` = plain
  code), `LOCATION_LABEL_BASE_URL` (default production, `https://alexander-warehouse.up.railway.app`).
- Scan / lookup: `/loc/<code>` (what the QR opens) and `/loc` with a scan box for scanner guns; any logged-in user, read only.
  Accepts the QR link, the plain code from the barcode, or a typed code. Shows the active Part 2 rows at that spot (matched by the old
  row/section/level values until stock is linked in step D). Not logged in: login, then back to the same spot.

## Part 2 locations, step C (same branch, not deployed)

- Admin page `/locations`: choose the row-size workbook (step A format) → **Preview** (reads only) → **Apply exactly this
  preview**. Choosing the file saves nothing.
- Apply refuses (nothing changed) when: a line is not marked OK; a number is invalid; an unknown special spot is listed; a
  spot that would be deactivated still holds stock; or the locations changed since the preview (plan hash, 409). Imports are
  serialized by an advisory lock and run in one transaction.
- Spots are created, deactivated or reactivated, never deleted; every change is a `location_changes` row with the admin's id.
- Stock that sits at spots outside the table is listed, never guessed. No inventory row or movement is touched; Allbirds is
  not read.
- API (ADMIN only): `POST /api/locations/import/preview`, `POST /api/locations/import/apply`, `GET /api/locations/summary`.
- New dependency: `openpyxl` (reads the .xlsx).

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
