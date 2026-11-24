# Handoff: WMS restructure (state on 2026-11-24)

**Phase 1a is deployed to production (2026-11-21).** No other code is deployed. **Production data:** on 2026-11-24 all Part 2 stock was replaced with the owner's full count through the /manage uploads (decision 7). Allbirds was not touched. The next deploy is 1b: do not deploy it until the open decisions below are made and `docs/DEPLOY_1B.md` has been followed.

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
   - Part 2 (Rows 1-16 since 2026-11-23, see decision 6) holds Von Dutch (VD), Valentino Orlandi (VO) and Ed Hardy (ED). Brand codes: **VD / VO / ED**.
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
     - stock in row 15 (146 rows), which is not in the app's Rows 1-14 location map (Part 2 is Rows 1-16: decision 6);
     - wall stock has no section number;
     - one row with section `Q`;
     - ~~one with level `14`~~ resolved 2026-11-23: Row 7 Section 8 "Level 14" is a typo, the real level is **4** (owner).
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
   - **Update 2026-11-24 (after the Part 2 replacement, decision 7):**
     - the duplicate groups in the live data are now all at qty 0 but still **active**:
       - EHBG-002 BLACK, Row 14 FRONT L1 (2 rows);
       - VDBP-039 CAMO, Row 4 S21 L1 (3 rows);
       - VDSB-2116 LIGHT DENIM, Row 11 BACK L1 (2 rows);
       - VOSB-030 BLACK, Row 12 BACK L2 (2 rows);
     - in the first two groups, one row now holds the new stock and the others are 0;
     - 0003 will still refuse to run until the extra rows are deactivated (1b feature) or otherwise resolved through the app;
     - pull a fresh Export CSV first: the old 11-rows/5-groups list is out of date.
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
6. **Part 2 layout and re-sectioned rows (owner's floor walk, 2026-11-23).**
   - **Physical layout, left to right:** Row 16 (single), 15/14, 13/12, 11/10, 9/8, 7/6, 5/4, 3/2 (double, back-to-back), Row 1 (single).
     - Wall along the back of all rows. Staging area in front of all rows.
     - **Part 2 = Rows 1-16** (not 1-14). The app's location map still says Rows 1-14.
   - **Rows 11, 12, 13 and 15 have been re-sectioned.** Their old WMS data is wrong and will be replaced.
   - **Row 15/16 new data:** `row_15-16_data.csv` (home PC, `C:\WMS-backups`): **154 lines / 8,620 pcs**. Decisions:
     - 1 line = 1 box, qty = PCS/BOX;
     - VDSB-2015 DENIM is gone from the warehouse;
     - `V-4013HUN` -> `VD-4013HUN`;
     - `VDAW-35` / `VDAW-50` / `VDAW-54` -> `VDAW-035` / `VDAW-050` / `VDAW-054`;
     - a size run (S/M/L/XL) = one mixed-size box;
     - VDAW-120 BLACK, Row 16 Sec 2 Lvl 1 = qty 0, to be counted.
   - **Rows 11-13 new data:** coming from the owner.
   - ~~Plan: one combined update of Rows 11, 12, 13, 15, 16~~ **superseded 2026-11-24 by the full Part 2 replacement (decision 7).**
   - The Row 15/16 upload had never reached production: the 2026-11-24 export had no Row 16.
   - **Stopped 2026-11-23 (work PC):** a separate "set Rows 11-13 to 0" upload was prepared but **not** built or run.
     Upload-page traps: see decision 7.
   - **Open layout questions:**
     - Ground Front = staging side, and Ground Back = wall side?
     - Where is the receiving door?
     - Wall: which sections and levels?
     - Are Rows 1-3, 10 and 14 still ground-only?
7. **Part 2 full replacement in PRODUCTION (done 2026-11-24, owner's explicit OK, uploads done by the owner).**
   - **Source:** `C:\WMS-backups\ALEXANDER INVENTORY(NANDU) - SORTED_INVENTORY.csv` (work PC; outside the repo).
     - Cleaned with owner-approved rules:
       - 1 entry = 1 box; a numeric BOX # = number of boxes; qty = boxes x PCS/BOX;
       - style fixes: spaces around "-" removed, V- -> VD-, V0 -> VO, VDAW-35/50/54 -> 035/050/054, size in brackets moved to size;
       - any other style text kept as written;
       - color typos fixed: MONGRAM, METALIC, a stray apostrophe.
     - Result: **1,503 entries, 1,533 boxes, 52,041 pcs.** That is 1,529 boxes / 52,009 pcs, plus the 2 QTY corrections (VDP-033, VDBP-025 = 3 boxes each).
   - **Files** (all in `C:\WMS-backups` on the work PC):
     - `export_before_part2.csv` (10:35), `export_mid_part2.csv`, `export_after_part2.csv`;
     - `part2_old_SET0.csv`, `part2_old_MANUAL.csv`, `part2_new_IN.csv`;
     - `part2_new_REPORT.txt` (the full cleaning report).
   - **Steps and numbers:**
     1. **Before:** Allbirds 8,610 rows / 209,206 pcs; old Part 2 1,266 rows / 42,222 pcs.
     2. **SET0 upload** (mode SET): 1,242 rows set to 0 (OUT -42,050).
        - The 9 duplicate rows (172 pcs) were zeroed by hand with **Adj** (STOCK_OUT).
        - Middle check: every Part 2 row at 0, Allbirds identical row by row.
     3. **IN upload** (mode IN): 1,443 lines; New 471, Updated 972, IN +52,041.
     4. **Final check passed:**
        - Allbirds identical row by row;
        - Part 2 = 52,041 pcs, 0 locations differ from the new count;
        - Part 2 rows: 1,737 = 1,429 with stock + 308 at 0.
        - The 308 rows at 0 are: 291 old locations not in the new count; 14 entries to count; 3 extra rows of the duplicate groups (EHBG-002, VDBP-039).
        - Nothing was deleted, and all history is kept.
   - **Open items:**
     - **14 entries loaded as qty 0, to be counted:**
       - VDAW-118 CHEETAH R4 S5 L1 (PCS/BOX 243);
       - VDAW-120 BLACK R16 S2 L1;
       - VDBP-050 DENIM R12 S10 L2 ("10/,8");
       - VDFW-017 (no color -> STANDARD) R4 S2 L4;
       - VDSB-2113 LIGHT DENIM R9 S30 L4 (PCS/BOX 2113);
       - VDSB-2116 DARK DENIM R8 S28 L1;
       - VDSB-2119BLK BLACK R8 S26 L1 and L2;
       - VOSB-027 ANIMAL PRINT R8 S25 L1;
       - VOSB-028 ANIMAL PRINT R8 S25 L2;
       - VOSB-028 LAVENDER R2 BACK L2 (".");
       - VOSB-029 ANIMAL PRINT R8 S25 L3;
       - VOSB-2119BLK BLACK R8 S27 L1 and L2.
     - **VOSB-037LAV LAVENDER SUEDE, Sec 13 Lvl 4, 20 pcs: NOT loaded** (no row in the count). Find its row.
       - Its other entry, R16 S11 L3 (120 pcs), was loaded.
     - **5 sizes guessed (not in the approved list) and loaded; confirm or fix in the app:**
       - VDAW-048 BLACK R12 S29 L3 "Sizes" -> MIX;
       - VDAW-048 BLUE R4 S2 L3 "MULTIPLE" -> MIX;
       - VDSB-2115 DARK DENIM R12 S22 L2 "XL & Mix" -> MIX;
       - VDTB-003 PINK FUR R12 S18 L2 "Large Medium" -> M/L;
       - VDSB-2114 DENIM R12 S23 L2 "2 diff styles" -> OS. Two styles are in one box; find out which.
     - **88 style codes are new to the WMS** (not in the old data, Part 1 or 2).
       - Most are genuine new styles (e.g. the Row 16 VDAW codes) or new because of the V- -> VD- rule.
       - **Check these "kept as written" ones; they may be variants of existing codes:**
         - `VDLBB-018 HP` (vs `VDLBB-018HP`);
         - `VDSB-2060 SIL`, `VDSB-2106 BLK`;
         - `VDSB-2119 BLU` / `RED` / `TEAL` (vs `VDSB-2119BLU` / `RED` / `TEAL`);
         - `VDP-2087 RED` (vs `VDP-2087`);
         - `VDBP-038/VOSB-030`, `VDAL-136`, `VDBP-1132`.
       - Also kept as written: VDBPP-033, "BLACK WITH ?", and the VDSB-2092BRWN / DBRN / DBROWN / DBRWN spellings.
       - Full list of the 88: EHSPE-006, VD-2001, VD-2022, VD-4013BLK, VD-4013BRN, VD-4013HUN, VD-4013WHT, VDAL-136,
         VDAW-001B, VDAW-043, VDAW-047, VDAW-051, VDAW-052, VDAW-054, VDAW-056, VDAW-057, VDAW-058, VDAW-059,
         VDAW-063, VDAW-064, VDAW-073, VDAW-074, VDAW-083, VDAW-085, VDAW-087, VDAW-090, VDAW-091, VDAW-092,
         VDAW-093, VDAW-094, VDAW-097, VDAW-098, VDAW-100, VDAW-101, VDAW-104, VDAW-105, VDAW-106, VDAW-107,
         VDAW-108, VDAW-110, VDAW-113, VDAW-120, VDAW-122, VDAW-124, VDAW-125, VDAW-126, VDAW-127, VDAW-128,
         VDAW-131, VDAW-132, VDAW-133, VDAW-136, VDAW-137, VDAW-139, VDBB-1113, VDBP-038/VOSB-030, VDBP-054,
         VDBP-1132, VDCB-001, VDLBB-018 HP, VDLBB-021, VDP-2068, VDP-2079PNK, VDP-2087 RED, VDSB-2005PNK,
         VDSB-2060, VDSB-2060 SIL, VDSB-2073, VDSB-2104, VDSB-2105, VDSB-2106 BLK, VDSB-2119 BLU, VDSB-2119 RED,
         VDSB-2119 TEAL, VDSB-2128, VDSB-2231, VDSB-2322, VDSB-2323, VOSB-014, VOSB-015, VOSB-037CRM, VOSB-037DBN,
         VOSB-037DPK, VOSB-037LAV, VOSB-055, VOSB-064, VOSB-079, VOSB-080.
     - **Size runs now use one format, `XS/S/M/L/XL`.** About 15 old rows stored them with commas (`XS,S,M,L,XL`); those old rows are at 0.
     - **Box counts are not stored** (BOX # left empty on purpose: see the traps below). They are in `part2_new_REPORT.txt`.
     - **1b / 0003:** the zeroed duplicate groups are still active rows. See decision 3, "Update 2026-11-24".
   - **Upload-page traps (`app/static/manage.js`, `/api/sheet-submit`), all found 2026-11-23/24:**
     - **The CSV upload saves the moment the file is picked.** There is no preview. Set the mode (IN/SET), staff and note first.
     - **QTY is the total when it is > 0.** With QTY 0 or empty, the page computes PCS/BOX x BOX # (or PCS/BOX).
       - So a zeroing or to-count line must have PCS/BOX empty.
     - **The page matches headers loosely.** Without an exact `BOX #` column, it reads **PCS/BOX as the box #**.
       - Every line would then miss its row and create a new one.
       - Always include an explicit (empty) `BOX #` column.
     - **A filled BOX # is part of the match.** It makes the upload create a new row instead of adding to the existing one.
     - **Duplicate rows (same style/color/size/location/box) can only be reached once.** Zero those by hand.
     - **The single-row SET EXACT QTY dialog exists (`setQtyModal`), but nothing opens it.** For a single row, use **Adj** with a minus amount.
       - It is recorded as STOCK_OUT under the login name.

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
