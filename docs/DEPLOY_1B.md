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
| Migration `0003` | Partial unique index: only **one active row per style + color + size + location (incl. box #)**. Deactivated rows don't count. If duplicates already exist, it **refuses and changes nothing** (see "Blocker" below). |
| `upgrade head` is all-or-nothing | All pending migrations run in one transaction. If 0003 fails, 0002 is rolled back too, and production stays at 0001. |
| Duplicate-slot writes → 409 | Creating, editing, reactivating or renaming into an occupied slot returns a clear 409 instead of a 500. Two sheet rows for the same new slot are merged into one row. |
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

## BLOCKER: duplicate active rows (migration 0003)

The inventory CSV import stores **one row per carton**. For example, 19 identical rows show TB1WJBK size 7 at Line 2 • Sec 1 • Lvl 4, each with 20 pcs and no box #. The new rule forbids that. On `warehouse_dev`, which holds the same CSV data, 0003 finds **258 slots with 608 active rows** and refuses. Production very likely has the same, plus any changes made since.

Consequences:
- Until the duplicates are resolved, `alembic upgrade head` fails and **1b cannot deploy**. It fails safely: nothing is changed and the old version keeps running.
- For the same reason, warehouse_dev stays at 0002, and the 1b app refuses to start on it.

Listing the duplicates needs **data**, not just the schema:
```powershell
python scripts/report_duplicate_active_rows.py duplicates.csv    # READ ONLY, DATABASE_URL = target DB
```
Running this against production reads production data, so it needs your explicit OK first.

How to resolve the duplicates is a business decision. Each option would be its own reviewed migration or script:
- **(a) Merge each group into one row.** Sum the quantities, keep one row, and deactivate the others with a 0-pc movement. History is kept.
- **(b) Number the cartons.** Give each carton row a box # so the rows become different slots.
- **(c) Change the rule.** Allow several rows per slot and drop 0003.

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

Migration 0003 was then **refused** on warehouse_dev (258 duplicate slots, nothing changed), so the database is at 0002.
