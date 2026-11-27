# Deploying Phase 1b (Alembic, protected history, deactivate)

**1b ships in two steps:**
- **1b-a** (branch `phase-1b-a`, this document): Alembic, migrations 0001, 0001a and 0002, protected history, deactivate. Head = **0002**.
- **1b-b** (branch `phase-1b-b`, made from `main` after 1b-a): migration 0003 (one active Part 2 row per slot). Deploy it only after the Part 2 duplicates are deactivated in the app (see "Migration 0003 comes later").

**Status:** 1b-a DEPLOYED to staging and production, 1b-b (0003) DEPLOYED to production, both on 2026-11-26. Production is at 0003; staging is still at 0002.
Deploy 1a first (`DEPLOY_1A.md`); 1b builds on it.

## Railway setup: read this first

- **No service reads `railway.json`.** The production main service has no Config-as-code path (checked 2026-11-26; staging is the same). The `preDeployCommand` and `startCommand` in `railway.json` **do not run**.
- **How the app starts:**
  - The dashboard Start command is empty, so Railway's builder uses the **`Procfile`**: `web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
  - 1b-a leaves the `Procfile` unchanged, so it starts exactly like 1a.
  - Confirm once in the dashboard: the latest deployment's details show this start command.
- **The migrations run from the dashboard:** Service → Settings → Deploy → **Pre-deploy step = `alembic upgrade head`**. Set it by hand, at the moment given in the deploy order below.
- **The 1b-a app refuses to start** unless the DB is at 0002. If it is deployed without the Pre-deploy step, it crash-loops and can replace the running 1a version. So the Pre-deploy step must be saved **before** the 1b-a deploy starts.
- **1a has no `alembic` installed.** Any 1a deployment that runs while the Pre-deploy step is set fails with "alembic: not found". Railway then aborts that deploy and keeps the running version. This is safe, but you must clear the field before rolling back to 1a.

## What changes for production

| Change | Effect |
|---|---|
| Alembic manages the schema | The app no longer runs `create_all` or `ALTER TABLE` at startup. It **refuses to start** if the DB is not at the latest migration (0002). |
| Dashboard Pre-deploy step `alembic upgrade head` | Railway runs the migrations before each deploy. If they fail, the deploy is aborted and the old version keeps running. |
| Migration `0001` (baseline) | Creates nothing on an existing DB. If the tables already exist without a stamp, it **refuses to run**. |
| Migration `0001a` | Brings an existing DB in line with the baseline: creates the 5 `inventory_items` indexes that the old startup code never made, and drops the old server defaults on `brand`/`warehouse_part`/`placement_type` (`'ALLBIRDS'`/`'PART_1'`/`'RACK'`; every insert path sets these itself). **Changes no rows.** On a fresh DB it does nothing. |
| Migration `0002` | `stock_movements.item_id` changes to `ON DELETE RESTRICT`, so the DB itself refuses to delete history. Adds `inventory_items.is_active BOOLEAN NOT NULL DEFAULT true` with an index. All existing rows stay active. No data is changed. |
| `upgrade head` is all-or-nothing | All pending migrations run in one transaction. If anything fails, production stays at 0001. |
| CSV export | Excludes deactivated rows. Admins get an extra "Export incl. Deactivated (Audit)" button that adds an ACTIVE column. Managers get 403 for that option. |
| Deactivate / reactivate | `POST /api/items/{id}/deactivate` and `/reactivate`, supervisor only. Deactivating requires quantity 0. Each change is recorded as a 0-pc `DEACTIVATE`/`REACTIVATE` movement under the logged-in user. |

## Migration 0003 comes later (1b-b)

0003 adds a **Part 2 only** partial unique index: one active row per location (row/section/level) + style + color + size + pack size.
- Deactivated rows don't count.
- Allbirds (Part 1, Lines) is not covered, and no data is changed anywhere.
- If Part 2 has duplicate active rows, 0003 refuses and changes nothing.

Production still has **4 Part 2 duplicate groups (5 extra rows, all at qty 0)**. This was checked on `export_after_part2_v2.csv` after the Part 2 replacement on 2026-11-24.

The sequence is:
1. Deploy 1b-a (this document). It contains no 0003, so the duplicates don't block it.
2. Deactivate the 5 extra rows **in the app**. Each one is recorded as a `DEACTIVATE` movement. Never use direct SQL.
3. Deploy 1b-b. The Pre-deploy step stays set, and `alembic upgrade head` applies 0003.

Run the duplicate check (`scripts/report_duplicate_active_rows.py`) again just before 1b-b. Against production it reads data, so it needs your explicit OK first.

Tested locally:
- An unstamped DB with Part 2 duplicates goes through `stamp 0001` → `upgrade head` = 0002, with no row or history changed.
- The full sequence 1b-a → deactivate → 1b-b → rollback passed.

## The database access window (steps 1–3)

Production Postgres has had no public access since 2026-11-21. Steps 1–3 run from your PC, so they need a short, planned access window. Do the same for staging.

1. **Open the window:** Railway → Postgres service → Settings → Networking → add a **TCP proxy**. Use its public URL for steps 1–3, only in one PowerShell window. Never write it to `.env` or the repo.
2. **Do steps 1, 2 and 3 in one sitting.**
3. **Close the window:**
   1. Remove the TCP proxy.
   2. **Regenerate the DB password** (Postgres service → Variables).
   3. Redeploy the **1a** main app so it connects with the new password. The Pre-deploy step must **not** be set yet.
   4. Check that the app works (dashboard loads, same totals).
4. **Order matters:** regenerate the password **before** setting the Pre-deploy step in step 4. Otherwise the redeploy needed for the new password runs 1a with the Pre-deploy step and is aborted ("alembic: not found").

## Step 1: check the schema against the baseline (read-only)

1. Make the schema-only dump. This is a read-only command; no data is exported.
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" --schema-only --no-owner --no-privileges `
       -f prod_schema.sql "<TCP proxy URL>"
   ```
   - Keep `prod_schema.sql` **outside the repo**, or delete it afterwards. Never commit it.
   - Use pg_dump 18. It can dump older servers.
2. Compare the dump with the baseline:
   ```powershell
   .venv\Scripts\python scripts\compare_schema.py docs\schema_baseline_0001.sql prod_schema.sql
   ```
3. Read the result:
   - **`IDENTICAL`:** go to step 2.
   - **Only the known drift that `0001a` fixes:** go to step 2. That drift is exactly 5 missing `inventory_items` indexes (`idx_item_part_line_sec`, `ix_inventory_items_brand`, `ix_inventory_items_location_code`, `ix_inventory_items_placement_type`, `ix_inventory_items_warehouse_part`) and `DEFAULT 'ALLBIRDS'`/`'PART_1'`/`'RACK'` on `brand`/`warehouse_part`/`placement_type`. Staging showed exactly this on 2026-11-26.
   - **Any other difference:** do **not** stamp. Close the access window (see above) and send me the diff. It is DDL only, with no data or passwords. I'll adjust the baseline, or add a migration `0001a` that brings production into line, and re-run the checks.

**Expected differences:**
- If production ever ran the old startup `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, then `brand`, `warehouse_part`, `placement_type` and `location_code` may carry server defaults (`DEFAULT 'ALLBIRDS'` and so on) that the baseline doesn't have.
- Other drift is possible on a database built by `create_all` over time, such as missing indexes or different nullability.
- Also look for stray v2 tables (`brands`, `products`, `skus`, ...). See HANDOFF.

## Step 2: back up (production)

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -Fc -f "C:\WMS-backups\wms_prod_before_1b_<date>.dump" "<TCP proxy URL>"
```

Store the backup outside the repo. Restoring it means `pg_restore --clean -d <url> file.dump`.

## Step 3: stamp (once per database)

Stamping tells Alembic "this DB already has the baseline". It writes only the `alembic_version` table. The running 1a app ignores that table, so stamping can happen before deploy day.

Run it from a `phase-1b-a` checkout, because 1a has no Alembic:
```powershell
$env:DATABASE_URL = "<TCP proxy URL>"      # only in this shell, then close it
.venv\Scripts\alembic stamp 0001
.venv\Scripts\alembic current               # -> 0001
```

Then close the access window: remove the proxy, regenerate the password, redeploy 1a, check.

## Deploy order (staging first, then production)

**Before you start (dashboard, read only):** for the main service, note:
- Settings → Source: which branch it deploys from, and whether automatic deployments are on;
- Deploy → Healthcheck path (expected: empty).

If automatic deployments are on for `main`, merging the PR **is** the deploy.

| # | Step | Staging | Production |
|---|---|---|---|
| 0 | Fresh data | Restore a current production dump into staging | (none) |
| 1 | Access window open; schema dump and compare | `IDENTICAL` or only the known `0001a` drift, else stop | `IDENTICAL` or only the known `0001a` drift, else stop |
| 2 | Backup | (none) | `wms_prod_before_1b_<date>.dump` |
| 3 | `alembic stamp 0001`, `alembic current` → `0001`; close the window (remove proxy, regenerate password, redeploy 1a, check) | yes | yes |
| 4 | **Settings → Deploy → Pre-deploy step = `alembic upgrade head`**. Leave Start command empty. | yes | yes, **right before step 5** |
| 5 | Deploy 1b-a | Point the staging main service at `phase-1b-a`; this starts the deploy | Merge the 1b-a PR into `main`; deploy |
| 6 | Deploy log | Pre-deploy shows `Running upgrade 0001 -> 0001a` and `Running upgrade 0001a -> 0002`; app log shows `[Database] Schema at migration 0002.` | same |
| 7 | Smoke checklist (below); dashboard totals unchanged | yes | yes |
| 8 | Rehearse the undo: clear Pre-deploy, redeploy 1a, check that 1a runs on 0002, set Pre-deploy again, redeploy 1b-a | yes | **no** |

**Notes:**
- **Step 4 may redeploy 1a.** If saving the Pre-deploy step ("Deploy staged changes") redeploys the current 1a deployment, that deploy fails at "alembic: not found" and is aborted. This is expected and harmless: 1a keeps running and the DB stays at 0001. Rehearse it on staging so it is no surprise on production.
- **Keep the Pre-deploy step set after 1b-a.** 1b-b (0003) and every later migration need it.
- **0002 is fast.** It adds a column with a constant default and swaps one foreign key. On about 10k rows this takes well under a second, with no table rewrite.

## Undo

| Situation | Undo |
|---|---|
| Only stamped (step 3), 1a running | Nothing needed: 1a works with the stamp. Leave it; the next attempt reuses it. |
| Pre-deploy step set (step 4), 1b-a not deployed | Clear the Pre-deploy field and save. The DB is unchanged at 0001. |
| 1b-a deploy failed in the Pre-deploy step | Railway aborted it and 1a keeps running. The migrations run in one transaction, so the DB stays at 0001. Clear the field, keep the log and stop. |
| 1b-a is running, you want 1a back | ① **First clear the Pre-deploy field** (otherwise the 1a redeploy fails at "alembic: not found"). ② Deployments → the previous 1a deployment → **Redeploy**. ③ The schema stays at 0002, which 1a works with: it ignores `is_active` (deactivated rows would just reappear), and RESTRICT only makes 1a's delete fail on rows with history, which 1a already blocks. ④ Optional, only with an explicit OK: `alembic downgrade 0001` from a `phase-1b-a` checkout, through an access window. It removes `is_active` and restores the CASCADE foreign key, with no rows deleted. |
| Last resort | Restore the step-2 backup. |

Downgrading below 0001 is refused unless `ALLOW_BASELINE_DOWNGRADE=1`. Never set that on production.

## Staging / smoke checklist (after deploy)

- [ ] The app starts and the log says `Schema at migration 0002`.
- [ ] Dashboard stats are unchanged from before the deploy (row count and units).
- [ ] Del (🗑️) on a row with qty > 0, with or without history: it asks to Deactivate instead; OK shows "Bring it to 0 first". Nothing is deleted, and the dashboard record count stays the same.
- [ ] Bring a test row to 0 with Adj, then Del, then OK: the row is deactivated and disappears from the dashboard, map and QR picking.
- [ ] Manage: no DELETE sheet mode/action and no "Delete Checked" button.
- [ ] Manage page, "Show deactivated rows": the row shows as Deactivated. Reactivate brings it back.
- [ ] The movement log shows DEACTIVATE/REACTIVATE with your name.
- [ ] QR picking and inbound approval still work.

## Local dev database

`warehouse_dev` went through this path:
1. Schema identical to the baseline.
2. Backup.
3. `stamp 0001`.
4. `upgrade head`.

Afterwards all 9,789 rows were active, total units were unchanged, and the history was intact.
