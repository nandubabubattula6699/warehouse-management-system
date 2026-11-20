# Deploying Phase 1b (Alembic, protected history, deactivate)

**Status: NOT deployable yet.** Production must first be compared with the baseline (step 1).
Deploy 1a first (`DEPLOY_1A.md`); 1b builds on it.

## What changes for production

| Change | Effect |
|---|---|
| Alembic manages the schema | The app no longer runs `create_all` or `ALTER TABLE` at startup. It **refuses to start** if the DB is not at the latest migration. |
| `railway.json` `preDeployCommand: alembic upgrade head` | Railway runs the migrations before each deploy. If they fail, the deploy is aborted and the old version keeps running. |
| Migration `0001` (baseline) | Creates nothing on an existing DB. If the tables already exist without a stamp, it **refuses to run**. |
| Migration `0002` | `stock_movements.item_id` changes to `ON DELETE RESTRICT`, so the DB itself refuses to delete history. Adds `inventory_items.is_active BOOLEAN NOT NULL DEFAULT true` with an index. All existing rows stay active. |
| Migration `0003` | **Part 2 (VD & VO, Rows) only.** Partial unique index: **one active row per location (row/section/level) + style + color + size + pack size**. Deactivated rows don't count. **Allbirds (Part 1, Lines) is not covered and no data is changed anywhere**: Lines keep one row per carton. If Part 2 already has duplicates, it **refuses and changes nothing** (see "Blocker" below). |
| `upgrade head` is all-or-nothing | All pending migrations run in one transaction. If 0003 fails, 0002 is rolled back too, and production stays at 0001. |
| Duplicate-slot writes → 409 (Part 2) | Creating, editing, reactivating or renaming into an occupied Part 2 slot returns a clear 409 instead of a 500. Two sheet rows for the same new Part 2 slot are merged into one row. Lines behave exactly as before. |
| CSV export | Excludes deactivated rows. Admins get an extra "Export incl. Deactivated (Audit)" button that adds an ACTIVE column. Managers get 403 for that option. |
| Deactivate / reactivate | `POST /api/items/{id}/deactivate` and `/reactivate`, supervisor only. Deactivating requires quantity 0. Each change is recorded as a 0-pc `DEACTIVATE`/`REACTIVATE` movement under the logged-in user. |

**Until step 3 is done, a 1b deploy fails safely.** The pre-deploy step stops at the 0001 guard, so nothing is deployed.

## Step 1: check the production schema against the baseline (read-only)

1. Make the schema-only dump. This is the one read-only production command you approved. No data is exported.
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" --schema-only --no-owner --no-privileges `
       -f prod_schema.sql "<PROD_SCHEMA_DUMP_URL from .env>"
   ```
   - Keep `prod_schema.sql` **outside the repo**, or delete it afterwards. Never commit it.
   - Use pg_dump 18. It can dump older servers.
2. Compare the dump with the baseline:
   ```powershell
   .venv\Scripts\python scripts\compare_schema.py docs\schema_baseline_0001.sql prod_schema.sql
   ```
3. Read the result:
   - **`IDENTICAL`:** go to step 2.
   - **Differences:** do **not** stamp. Send me the diff (it is DDL only, with no data or passwords). I'll adjust the baseline, or add a migration `0001a` that brings production into line, and re-run the checks.

   **Expected difference:** if production ever ran the old startup `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, then `brand`, `warehouse_part`, `placement_type` and `location_code` may carry server defaults (`DEFAULT 'ALLBIRDS'` and so on) that the baseline doesn't have. Other drift is possible on a database built by `create_all` over time, such as missing indexes or different nullability.

## BLOCKER: Part 2 duplicate active rows (migration 0003)

Allbirds (Part 1, Lines) is out of scope: one row per carton is normal there and is never reported or changed.

On `warehouse_dev`, 0003 finds **5 Part 2 slots with 11 active rows** and refuses (nothing changed):

| Brand | Style / color / pcs per box | Location | Rows |
|---|---|---|---|
| Von Dutch | VDBP-039 / CAMO / 8 | Row 4 • Sec 21 • Lvl 1 | 3 |
| Von Dutch | VDSB-2116 / LIGHT DENIM / 48 | Row 11 • Ground BACK • Lvl 1 | 2 |
| Valentino | VOSB-030 / BLACK / 10 | Row 12 • Ground BACK • Lvl 2 | 2 |
| Ed Hardy | EHBG-002 / BLACK / 16 | Row 14 • Ground FRONT • Lvl 1 | 2 |
| Ed Hardy | EHSPE-001 / PINK / 24 | Row 15 • Ground FRONT • Lvl 1 | 2 |

Production may differ.

Consequences:
- Until Part 2 is clean, `alembic upgrade head` fails and **1b cannot deploy**. It fails safely: nothing is changed and the old version keeps running.
- For the same reason, warehouse_dev stays at 0002, and the 1b app refuses to start on it.

Listing the duplicates needs **data**, not just the schema:
```powershell
python scripts/report_duplicate_active_rows.py duplicates.csv    # READ ONLY, DATABASE_URL = target DB
```
Running this against production reads production data, so it needs your explicit OK first.

**Plan (decided):** VD & VO get new locations (format `R<row>-S<section>-<level>`, e.g. `R3-S5-2`) and a fresh initial count. Their old rows are replaced, not merged. That replacement is a separate, reviewed step. 0003 can only be applied once Part 2 has no duplicate active rows.

Verified on a throw-away copy of warehouse_dev:
- **Duplicates present:** 0003 refuses and the DB stays at 0002.
- **Duplicates cleared (on the copy only):** 0003 applies.
- **Both cases:** all 14 Lines are identical before and after: 8,610 rows, 209,162 pcs, 14,632 boxes, every row and its history.

## Step 2: back up production

Do this immediately before migrating, from a machine with pg_dump 18:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -Fc -f "wms_prod_before_1b_<date>.dump" "<prod URL>"
```

Store the backup somewhere safe, not in the repo. Restoring it means `pg_restore --clean -d <url> file.dump`.

## Step 3: stamp production (once)

Stamping tells Alembic "this DB already has the baseline". It writes only the `alembic_version` table.

```powershell
$env:DATABASE_URL = "<prod URL>"      # only in this shell, then close it
.venv\Scripts\alembic stamp 0001
.venv\Scripts\alembic current           # -> 0001
```

## Step 4: deploy

Do this only after the blocker above is resolved. Merge the 1b PR, then deploy. Railway runs `alembic upgrade head`, which applies 0002 and 0003 in a single transaction, and only then starts the app.
- Check the deploy log for `Running upgrade 0002 -> 0003` and `[Database] Schema at migration 0003.`
- 0002 adds a column with a constant default and swaps one foreign key. On about 10k rows this takes well under a second, with no table rewrite.

## Staging / smoke checklist (after deploy)

- [ ] The app starts and the log says `Schema at migration 0002`.
- [ ] Dashboard stats are unchanged from before the deploy (row count and units).
- [ ] Delete a row that has history: you get a 409 and are asked "Deactivate this row now instead?". Answering OK with qty > 0 shows "Bring it to 0 first".
- [ ] Bring a test row to 0 with Adj, then Del, then OK: the row disappears from the dashboard, map and QR picking.
- [ ] Manage page, "Show deactivated rows": the row shows as Deactivated. Reactivate brings it back.
- [ ] The movement log shows DEACTIVATE/REACTIVATE with your name.
- [ ] QR picking and inbound approval still work.

## Rollback

- **Code only:** redeploy the previous (1a) deployment in Railway. The 1a code works with the 0002 schema: it ignores `is_active`, and deactivated rows would just reappear. RESTRICT only makes 1a's delete fail on rows with history, and 1a already blocks those.
- **Schema:** `alembic downgrade 0002` drops only the unique index. `alembic downgrade 0001` (with DATABASE_URL set to prod) removes `is_active` and restores the CASCADE foreign key. No rows are deleted. Downgrading below 0001 is refused unless `ALLOW_BASELINE_DOWNGRADE=1`. Never set that on production.
- **Last resort:** restore the step-2 backup.

## Local dev database

`warehouse_dev` went through exactly this path:
1. Schema identical to the baseline.
2. Backup.
3. `stamp 0001`.
4. `upgrade head`.

Afterwards all 9,789 rows are active, total units are unchanged, and the history is intact.

Migration 0003 was then **refused** on warehouse_dev (5 Part 2 duplicate slots, nothing changed), so the database is at 0002.
