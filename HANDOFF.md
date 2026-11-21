# Handoff: WMS restructure (state on 2026-11-20)

**Nothing has been deployed.** Railway and production are unchanged. Do not deploy until the open decisions below are made and the deploy docs have been followed.

## 1. Phase status

| Phase | Branch | Done | Tested | Pushed | Deployed |
|---|---|---|---|---|---|
| 0: audit and target architecture | `phase-0-audit` | yes | n/a (docs) | yes | n/a |
| 1a: emergency fixes (auth on every route, secrets, CORS, XSS, data safety) | `phase-1a-emergency-fixes` | yes | yes, automated tests + browser checks | yes | **NOT deployed** |
| 1b: foundation (Alembic, protected history, deactivate, 0003, ruff, CI) | `phase-1b-foundation` (built on 1a) | yes, except the open decisions below | yes: 65 main-app + 9 picking-service tests, ruff clean, migration up/down on a fresh DB | yes | **NOT deployed** |

**Pull requests:** none are open yet (no `gh` CLI here). Open them on GitHub:
- **1a:** `phase-1a-emergency-fixes` → `main`
- **1b:** `phase-1b-foundation` → `phase-1a-emergency-fixes`. Retarget it to `main` after 1a is merged.

**Local dev database (old PC only):**
- `warehouse_dev` is at migration **0002**.
- Migration 0003 refuses to run there because Part 2 has 5 duplicate groups (11 rows). This is intended: see decision 3.
- The 1b app refuses to start until the DB is at the newest migration (0003).

## 2. Open decisions (waiting for you)

1. **Ed Hardy.**
   - 94 Ed Hardy rows are stored as Part 2 (Rows), together with VD & VO.
   - Two of the 5 Part 2 duplicate groups are Ed Hardy (EHBG-002, EHSPE-001).
   - Decide:
     - Is Ed Hardy covered by the Part 2 one-row-per-slot rule?
     - Is it included in the VD/VO relocation and fresh count?
2. **VD/VO relocation step (not built yet).**
   - **Planned:** VD & VO get new locations (`R<row>-S<section>-<level>`, e.g. `R3-S5-2`) and a fresh initial count. Their old rows are replaced, not merged.
   - **Needed from you:** the go-ahead and the details:
     - the new location list;
     - how the count is entered;
     - what happens to the old rows (deactivate, keeping their history).
3. **0003 duplicates scope (decided, recorded here).**
   - **Allbirds (Part 1, Lines) is untouched.** It keeps one row per carton, and no migration changes any data.
   - The unique rule covers only Part 2 (VD & VO, Rows): location + style + color + size + pack size.
   - 0003 refuses to run while Part 2 has duplicates.
   - **Still to confirm:**
     - "pack size" = pieces per box (10 rows have none and count as 0);
     - box # is not part of the location.
   - Details: `docs/DEPLOY_1B.md`, section "BLOCKER".
4. **Receiving-check plan: ON HOLD.** Decide whether to build it inside the WMS (as `modules/inbound`) or separately.
   - The revised plan was: same Postgres in its own schema `receiving_check`, WMS logins and roles read-only, Postgres 18 everywhere.
   - Still open within that plan:
     - the login model (shared accounts with its own session, vs. the same session);
     - whether Part 1/Part 2 leads are workers or supervisors;
     - async vs. sync DB driver.
   - Nothing was built. The only receiving-check files are the earlier Antigravity attempt in `C:\Users\Nancy Arroyo\receiving-check-backup` on the old PC. That folder is not a git repo, was never pushed, and contains a `.env` (secrets).
5. **Possible stray v2 tables in production.**
   - Check whether production already has the tables `brands`, `products`, `skus`, `sku_barcodes`, `zones`, `bins`, `lpns`, `inventory_balances`, `inventory_txns` (possible `create_all` from the home PC on Nov 19).
   - Verify this during the production schema check, before the 1b baseline is stamped.
   - The draft model is saved on branch `draft/wms-models-v2` (NOT for merge; input for Phase 3 design).

## 3. Things you must do in Railway

- [ ] **Remove public access to the production Postgres** (`DATABASE_PUBLIC_URL` / TCP proxy), unless something still needs it. Do this after taking the 1b schema dump below.
- [ ] **Change the production DB password.** Then update `DATABASE_URL` on every service that uses it.
- [ ] **Delete the `receiving-check-dev` service**, later, once the receiving-check decision is made.
- [ ] **Take the production schema dump for 1b.**
  - Run `pg_dump --schema-only` (no data) and compare it with `docs/schema_baseline_0001.sql`. Steps: `docs/DEPLOY_1B.md`, step 1.
  - Keep the dump outside the repo.

## 4. Deploy order (when you decide to deploy, not before)

1. **1a via staging:** follow `DEPLOY_1A.md` (staging environment → checklist §5 → production).
2. **Then 1b:** follow `docs/DEPLOY_1B.md`:
   - schema dump and compare;
   - resolve the Part 2 duplicates;
   - back up production;
   - `alembic stamp 0001`;
   - deploy (Railway runs `alembic upgrade head` before starting the app).

## 5. New PC setup (Windows)

1. **Install:**
   - Git;
   - Python 3.12 (tick "Add to PATH");
   - PostgreSQL 18 (remember the `postgres` password; installer default port 5432);
   - Node 22 LTS (for JS syntax checks).
2. **Clone the repo and switch to the branch:**
   ```powershell
   cd $HOME\IdeaProjects
   git clone https://github.com/nandubabubattula6699/warehouse-management-system.git
   cd warehouse-management-system
   git checkout phase-1b-foundation
   ```
3. **Create the virtual environment and install requirements:**
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   ```
4. **Create `.env`** (copy `.env.example`) with your **local** database only. Never put the production URL here.
   ```
   DATABASE_URL=postgresql://postgres:<local password>@localhost:5432/warehouse_dev
   ```
   - URL-encode special characters in the password (e.g. `@` → `%40`).
   - Set `INTERNAL_API_KEY` and `PICK_DEVICE_TOKENS` to any long random local values.
5. **Create the databases and build the schema:**
   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres warehouse_dev
   & "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres warehouse_test
   .venv\Scripts\alembic upgrade head        # builds the empty schema in warehouse_dev
   ```
   - The new `warehouse_dev` is empty. The old PC's dev data (a copy of the inventory CSV) is not in git.
   - Load inventory only if you need it, with `scripts/migrate_inventory.py`. See the README.
6. **Run the checks:**
   ```powershell
   .venv\Scripts\ruff check .
   .venv\Scripts\python -m pytest -q                       # expect 65 passed
   cd services\picking-service; ..\..\.venv\Scripts\python -m pytest -q; cd ..\..   # expect 9 passed
   ```

## 6. What to tell Claude Code on the new PC

Open Claude Code in the repo folder and paste:

> Read HANDOFF.md, WMS_Restructure_Prompt.md, docs/CHANGELOG.md and docs/DEPLOY_1B.md. We are on branch
> phase-1b-foundation. Nothing is deployed. Do not deploy, do not push to main, and never run anything
> against the production database unless I explicitly say so in that message. First verify my new PC
> setup (section 5): .venv, .env pointing at a LOCAL database, warehouse_dev and warehouse_test exist,
> `alembic upgrade head`, ruff and both test suites pass. Report the results. Then wait for my
> decisions on the open items in section 2 before changing anything.
