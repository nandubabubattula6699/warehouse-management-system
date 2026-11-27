# Handoff: WMS restructure (state on 2026-11-21)

**Phase 1a is deployed to production (2026-11-21).** Nothing else is deployed. The next deploy is 1b: do not deploy it until the open decisions below are made and `docs/DEPLOY_1B.md` has been followed.

## 1. Phase status

| Phase | Branch | Done | Tested | Pushed | Deployed |
|---|---|---|---|---|---|
| 0: audit and target architecture | `phase-0-audit` | yes | n/a (docs) | yes | n/a |
| 1a: emergency fixes (auth on every route, secrets, CORS, XSS, data safety) | `phase-1a-emergency-fixes` | yes | yes, automated tests + browser checks, then a Railway staging environment | yes | **DEPLOYED 2026-11-21** (`main` = `a8b3af8`) |
| 1b: foundation (Alembic, protected history, deactivate, 0003, ruff, CI) | `phase-1b-foundation` (built on 1a) | yes, except the open decisions below | yes: 65 main-app + 9 picking-service tests, ruff clean, migration up/down on a fresh DB | yes | **NOT deployed** |

**1a deploy (2026-11-21):**
- `main` was fast-forwarded to `phase-1a-emergency-fixes` (`a8b3af8`), after testing on a Railway staging environment.
- Picking uses per-device tokens. 5 devices are registered: `phone-1`, `phone-2`, `phone-3`, `scanner-1`, `scanner-2`.
- **Lesson for future staging:** after duplicating an environment, check every URL variable. In staging,
  `INVENTORY_SERVICE_URL` still pointed to production.

**Pull requests:**
- **1a:** done (merged into `main` by fast-forward).
- **1b:** `phase-1b-foundation` → `main` (the PR now targets `main`). This is the next deploy.

**Local dev database (old PC only):**
- `warehouse_dev` is at migration **0002**.
- Migration 0003 refuses to run there because Part 2 has duplicates: 11 rows in 5 groups. This is intended: see decision 3.
- The 1b app refuses to start until the DB is at the newest migration (0003).

## 2. Open decisions (waiting for you)

1. **Ed Hardy (decided 2026-11-21).**
   - Part 2 (Rows 1-14) holds Von Dutch (VD), Valentino Orlandi (VO) and Ed Hardy (ED). Brand codes: **VD / VO / ED**.
   - **Ed Hardy is treated exactly like VD & VO:** Part 2, one-active-row rule, relocation and fresh count.
   - 0003 already covers it: the index filters on `warehouse_part = 'PART_2'`, and `app/location_engine.py` assigns ED HARDY to Part 2. No code change needed.
   - 94 Ed Hardy rows are in Part 2. Of the Part 2 duplicates (11 rows in 5 groups), two groups are Ed Hardy (EHBG-002, EHSPE-001); they are fixed together with the VD/VO ones.
   - **Do NOT rename the stored value `PART_2_VD_VALENTINO`.** It is saved on user records (`assigned_zone`), so renaming it needs a data migration. Later we may change only the display text.
2. **VD/VO/ED relocation step (not built yet; go-ahead given 2026-11-21: build it AFTER 1a + 1b are deployed).**
   - **Planned:** VD, VO & ED get new locations and a fresh initial count. Their old rows are replaced, not merged.
   - **Part 2 location names (decided 2026-11-21; replaces the old "level = number" rule). Every location always has a level:**
     - shelf `R<row>-S<section>-L<level>` (e.g. `R3-S5-L2`);
     - ground front `R<row>-GF-L<level>`; ground back `R<row>-GB-L<level>`;
     - wall `W-S<section>-L<level>`;
     - special `R-RECV`, `R-STAGE`, `R-DAMAGE`.
   - **Draft layout (2026-11-21):** `C:\WMS-backups\part2_layout_draft.xlsx` (outside the repo, from a local restore of that morning's backup). Every spot must be confirmed on the floor. Found, to check on the floor:
     - stock in row 15 (146 rows), which is not in the app's Rows 1-14 location map;
     - wall stock has no section number;
     - one row with section `Q`, one with level `14`.
   - **Allbirds (Part 1): PLANNED, NOT NOW.** Future format `LN<line>-S<section>-L<level>` (e.g. `LN1-S1-L1`). Needs a separate approved project: reprint the 501 QR labels, update the picking-service, test on staging. Allbirds data stays unchanged until then.
   - **Needed from you:** the go-ahead and the details:
     - the new location list;
     - how the count is entered;
     - what happens to the old rows (deactivate, keeping their history).
3. **0003 duplicates scope (decided, recorded here).**
   - **Allbirds (Part 1, Lines) is untouched.** It keeps one row per carton, and no migration changes any data.
   - The unique rule covers only Part 2 (VD, VO & ED, Rows): location + style + color + size + pack size. Scope agreed 2026-11-21.
   - 0003 refuses to run while Part 2 has duplicates.
   - **The duplicates (11 rows in 5 groups, counted on the old PC's warehouse_dev copy) are fixed only through the app** (adjustment / deactivate, recorded as movements), never by direct SQL. List them first and show them to the owner.
   - **Duplicate list (decided 2026-11-21):** use the normal Export CSV from the live WMS, but NOT now. Pull it right before fixing the duplicates during 1b, so the list is current.
   - **Still to confirm:**
     - "pack size" = pieces per box (10 rows have none and count as 0);
     - box # is not part of the location.
   - Details: `docs/DEPLOY_1B.md`, section "BLOCKER".
4. **Receiving-check plan: ON HOLD.** Decided 2026-11-21: build it inside the WMS (as `modules/inbound`), not separately. Still on hold.
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

- [x] **Remove public access to the production Postgres** (TCP proxy removed, reported 2026-11-21).
- [x] **Change the production DB password** (regenerated, reported 2026-11-21).
- [ ] **Delete the `receiving-check-dev` service and the staging environment** when they are no longer needed.
- [ ] **Rotate the production `INTERNAL_API_KEY` and the picking device tokens.** They appeared in screenshots.
- [ ] **Retire the old `nandu` / `manager` accounts.** Create the new personal admin account first.
- [ ] **Take the production schema dump for 1b.**
  - Run `pg_dump --schema-only` (no data) and compare it with `docs/schema_baseline_0001.sql`. Steps: `docs/DEPLOY_1B.md`, step 1.
  - Keep the dump outside the repo.

## 4. Deploy order (when you decide to deploy, not before)

1. **1a via staging:** done 2026-11-21.
2. **Next: 1b:** follow `docs/DEPLOY_1B.md`:
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
> phase-1b-foundation. Only 1a is deployed (main = a8b3af8). Do not deploy, do not push to main, and never run anything
> against the production database unless I explicitly say so in that message. First verify my new PC
> setup (section 5): .venv, .env pointing at a LOCAL database, warehouse_dev and warehouse_test exist,
> `alembic upgrade head`, ruff and both test suites pass. Report the results. Then wait for my
> decisions on the open items in section 2 before changing anything.
