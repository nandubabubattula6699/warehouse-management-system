# Handoff: WMS restructure (state on 2026-11-26)

**Phase 1a (2026-11-21) and Phase 1b-a (2026-11-26) are deployed to production** (`main` = `d9f1811`, PR #1). Production is at migration **0002**. **Production data:** on 2026-11-24 all Part 2 stock was replaced through the /manage uploads (decision 7): 54,878 pcs. The next deploy is **1b-b** (migration 0003, branch `phase-1b-b`): first deactivate the Part 2 duplicate rows in the app (decision 3).

## 1. Phase status

| Phase | Branch | Done | Tested | Pushed | Deployed |
|---|---|---|---|---|---|
| 0: audit and target architecture | `phase-0-audit` | yes | n/a (docs) | yes | n/a |
| 1a: emergency fixes (auth on every route, secrets, CORS, XSS, data safety) | `phase-1a-emergency-fixes` | yes | yes, automated tests + browser checks, then a Railway staging environment | yes | **DEPLOYED 2026-11-21** (`a8b3af8`) |
| 1b-a: Alembic (0001, 0001a, 0002), protected history, deactivate, never hard-delete, ruff, CI | `phase-1b-a` (merged into `main` via PR #1) | yes | yes: 63 main-app + 9 picking-service tests, ruff clean; full staging rehearsal incl. undo | yes | **DEPLOYED 2026-11-26** (`main` = `d9f1811`) |
| 1b-b: migration 0003 (one active Part 2 row per slot) | `phase-1b-b` (from `main` `d9f1811` + 0003) | yes | yes: 69 main-app (0 skipped) + 9 picking-service tests, ruff clean | yes | **NOT deployed** |
| (old) 1b in one step | `phase-1b-foundation` | superseded by 1b-a + 1b-b | | yes | do not deploy |

**1b-a deploy (2026-11-26).** Steps and lessons (details: `docs/DEPLOY_1B.md`):
- **Railway does not read `railway.json`** (no Config-as-code path on any service). The app starts from the `Procfile`. The migrations run from the dashboard **Pre-deploy step `alembic upgrade head`**, which is now **set on both staging and production** and stays set for 1b-b and every later migration.
- **Schema drift found:** staging and production lacked 5 `inventory_items` indexes and had 3 old server defaults (`'ALLBIRDS'`/`'PART_1'`/`'RACK'`). Fixed by the new migration **0001a** (no row changes; chain 0001 → 0001a → 0002). `scripts/compare_schema.py` now ignores column order. No stray v2 tables in staging or production (decision 5 resolved).
- **Railway's Postgres adds a hidden `pg_attver` column option** to columns created after the first dump (seen on staging for `is_active` and `alembic_version`). It is not a schema difference; the compare shows it as one line.
- **Staging rehearsal (2026-11-26):** access window (TCP proxy), compare, stamp 0001, Pre-deploy step + branch switch in one deploy (0001 → 0001a → 0002), read-only checks, smoke test, undo rehearsal (Pre-deploy cleared + back to 1a: 1a runs fine on 0002; then back to 1b-a), proxy removed, password regenerated. Staging now runs 1b-a.
- **Hard-delete gap found on staging and closed.** In 1a, Del removed any row **without movement history**, stock included, with no record (staging lost TR3WKWW 10 pcs and VDSB-2117 48 pcs during the smoke test). 1b-a: **the app never hard-deletes inventory rows**; Del, bulk delete and the sheet DELETE action return 409 and point to Deactivate (cache-buster v36).
- **Production steps:** read-only counts → schema compare (only the known 0001a drift) → backup → stamp 0001 → window closed (proxy removed, password regenerated, 1a redeployed) → Pre-deploy step + PR #1 merged → deploy log `0001 -> 0001a`, `0001a -> 0002`, `Schema at migration 0002`, 10,490 records → smoke test OK.
- **Production numbers at the deploy:** Allbirds **8,609 rows / 209,191 pcs**; Part 2 **1,881 rows / 54,878 pcs**; 5,857 movements.
- **Backup before 1b:** `C:\WMS-backups\wms_prod_before_1b_2026-11-26.dump` (home PC, 696,153 bytes). Verified by `pg_restore --list` and a full test restore with identical counts.
- **Finding: Allbirds row deleted without trace.** Production id **549**, A11079 / STANDARD / size 8, Line 2 • Sec 1 • Lvl 1, **15 pcs**, no history, is gone (deleted between 2026-11-24 and 2026-11-26 through the 1a hard-delete gap). It was one of two identical cartons; its twin id 550 (15 pcs) is still there. The owner accepted the new baseline and decided **not to re-add anything**. A floor count of A11079 size 8 at that spot would show whether a carton is really missing; any correction only through the app.
- **Windows on the home PC blocks `alembic.exe`** (Application Control policy). Use `.venv\Scripts\python -m alembic ...`.

**1a deploy (2026-11-21):**
- `main` was fast-forwarded to `phase-1a-emergency-fixes` (`a8b3af8`), after testing on a Railway staging environment.
- Picking uses per-device tokens. 5 devices are registered: `phone-1`, `phone-2`, `phone-3`, `scanner-1`, `scanner-2`.
- **Lesson for future staging:** after duplicating an environment, check every URL variable. In staging,
  `INVENTORY_SERVICE_URL` still pointed to production.

**Pull requests:**
- **1a:** done (merged into `main` by fast-forward).
- **1b-a:** done (PR #1, merged 2026-11-26).
- **1b-b:** `phase-1b-b` → `main`. No PR yet. Open it only after the duplicates are deactivated in production.

**Local dev database (old PC only):**
- `warehouse_dev` is at migration **0002** (before 0001a was added).
- Migration 0003 refuses to run there because Part 2 has duplicates: 11 rows in 5 groups. This is intended: see decision 3.
- The 1b-b app refuses to start until the DB is at the newest migration (0003).

**Home PC:** local PG18 on port 5433 keeps `prod_restore_check` (restore of the 2026-11-21 backup, read-only use). The throwaway test databases from 2026-11-26 were dropped.

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
   - **Update 2026-11-24 (after the v2 Part 2 replacement, decision 7):** 4 duplicate groups (9 rows) are still **active**.
     Checked with 0003's exact key (row/section/level + style + color + size + pcs/box) on `export_after_part2_v2.csv`:

     | Style / color / size | Pcs/box | Location | Qty per row | Rows to deactivate |
     |---|---|---|---|---|
     | VDBP-039 CAMO OS | 8 | Row 4 S21 L1 | 24, 0, 0 | the two 0 rows |
     | EHBG-002 BLACK OS | 16 | Row 14 FRONT L1 | 32, 0 | the 0 row |
     | VDSB-2116 LIGHT DENIM OS | 48 | Row 11 BACK L1 | 0, 0 | one, or both (not in the count) |
     | VOSB-030 BLACK OS | 10 | Row 12 BACK L2 | 0, 0 | one, or both (not in the count) |

     - EHSPE-001 is no longer a duplicate. The old 11-rows/5-groups list is out of date.
     - All rows to deactivate are at qty 0, as 1b's Deactivate requires.
     - **0003 will refuse to run until they are deactivated.**
     - Proposed (planning 2026-11-24, not yet approved), deploy 1b in two steps:
       1. 1b without 0003; then deactivate the 5 rows in the app;
       2. then 0003.
     - Pull a fresh Export CSV right before, in case Part 2 changed.
   - **Update 2026-11-26:** step 1 is done (1b-a deployed). Next: pull a fresh export, check the groups again
     (`scripts/report_duplicate_active_rows.py` against production needs the owner's OK), deactivate the extra rows in the
     app (each one a recorded `DEACTIVATE` movement), then deploy 1b-b. Staging holds older data (2026-11-21), so its
     duplicate list differs: check it there too before the 1b-b staging deploy.
4. **Receiving-check plan: ON HOLD.** Decided 2026-11-21: build it inside the WMS (as `modules/inbound`), not separately. Still on hold.
   - The revised plan was: same Postgres in its own schema `receiving_check`, WMS logins and roles read-only, Postgres 18 everywhere.
   - Still open within that plan:
     - the login model (shared accounts with its own session, vs. the same session);
     - whether Part 1/Part 2 leads are workers or supervisors;
     - async vs. sync DB driver.
   - Nothing was built. The only receiving-check files are the earlier Antigravity attempt in `C:\Users\Nancy Arroyo\receiving-check-backup` on the old PC. That folder is not a git repo, was never pushed, and contains a `.env` (secrets).
5. **Possible stray v2 tables in production: RESOLVED 2026-11-26.** The schema dumps of staging and production have none of
   `brands`, `products`, `skus`, `sku_barcodes`, `zones`, `bins`, `lpns`, `inventory_balances`, `inventory_txns`.
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
7. **Part 2 full replacement in PRODUCTION (2026-11-24, owner's explicit OK, uploads done by the owner).**
   - **Current state = v2 (the "original" full count, 12:10-12:21).** It replaced the morning run (v1).
   - **Cleaning rules** (owner-approved, same for v1 and v2):
     - 1 entry = 1 box; a numeric BOX # = number of boxes; qty = boxes x PCS/BOX;
     - style fixes: spaces around "-" removed, V- -> VD-, V0 -> VO, VDAW-35/50/54 -> 035/050/054, size in brackets moved to size;
     - any other style text kept as written;
     - color typos fixed: MONGRAM, METALIC, a stray apostrophe;
     - safe defaults for v2 (owner): no PCS/BOX -> qty 0 "to be counted"; unclear style -> kept as written;
       no row -> not loaded; unclear size -> MIX.
   - **v2 source:** `C:\WMS-backups\part2_original_v2.csv` (work PC; outside the repo).
     - **1,624 entries, 1,654 boxes, 54,878 pcs.** That is 1,650 boxes / 54,846 pcs, plus the 2 QTY corrections (VDP-033, VDBP-025 = 3 boxes each).
     - Compared with v1, only Rows 12 and 13 differ. Row 12: 135 entries / 3,401 pcs. Row 13: 128 / 3,412.
   - **v2 files** (all in `C:\WMS-backups` on the work PC):
     - `part2_original_v2.csv`;
     - `export_before_part2_v2.csv` (12:11), `export_mid_part2_v2.csv` (12:16), `export_after_part2_v2.csv` (12:21);
     - `part2_v2_SET0.csv`, `part2_v2_MANUAL.csv`, `part2_v2_IN.csv`;
     - `part2_v2_REPORT.txt` (the full cleaning report).
   - **v2 steps and numbers:**
     1. **Before** (= the v1 result): Allbirds 8,610 rows / 209,206 pcs; Part 2 1,737 rows / 52,041 pcs.
     2. **SET0 upload** (mode SET): 1,427 rows set to 0 (OUT -51,985).
        - 2 duplicate rows were zeroed by hand with **Adj**: EHBG-002 -32, VDBP-039 -24.
        - Middle check: every Part 2 row at 0, Allbirds identical row by row.
     3. **IN upload** (mode IN): 1,564 lines, IN +54,878.
        - The export shows exactly 144 new rows, so the banner was New 144 / Updated 1,420.
        - The owner's message did not fill in these two numbers.
     4. **Final check passed:**
        - Allbirds identical row by row (8,610 / 209,206);
        - Part 2 = 54,878 pcs, 0 locations differ from the v2 count;
        - Part 2 rows: 1,881 = 1,550 with stock + 331 at 0.
        - The 331 rows at 0 are: 314 old locations not in the count; 14 entries to count; 3 extra rows of the duplicate groups (EHBG-002, VDBP-039).
        - Nothing was deleted, and all history is kept.
   - **v1 (morning, now superseded):**
     - Source: `ALEXANDER INVENTORY(NANDU) - SORTED_INVENTORY.csv`. 1,503 entries / 1,533 boxes / 52,041 pcs.
     - Steps: SET0 1,242 rows (OUT -42,050), 9 manual zeros, then IN 1,443 lines (New 471, Updated 972).
     - Before v1: Part 2 was 1,266 rows / 42,222 pcs. Allbirds 8,610 / 209,206, unchanged throughout.
     - **The v1 files are missing from `C:\WMS-backups`** (found gone around 12:00 on 2026-11-24): the source, the three exports and the upload files.
       - Check the Recycle Bin. The numbers above are the only record.
   - **Open items:**
     - **14 entries loaded as qty 0, to be counted** (the same in v1 and v2):
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
     - **VOSB-037LAV:** v2 has only R16 S11 L3 (120 pcs), which was loaded.
       - v1's extra entry without a row (Sec 13 Lvl 4, 20 pcs) is not in v2.
     - **Unclear sizes in v2 (safe defaults applied); confirm or fix in the app:**
       - VDAW-048 BLUE R4 S2 L3: "MULTIPLE" -> MIX;
       - VDZU-031 PURPLE R13 S18 L2: "Sizes" -> MIX;
       - `VDAW-139 & 129` HOT PINK - YELLOW R13 S12 L1: "2 diff styles" -> MIX. Style kept as written: one box holds two styles.
       - VDAW-128 BLACK R13 S7 L1: the style says (M), but BOX # says "Large Medium" -> M (the bracket wins);
       - VDAW-129 YELLOW R13 S11 L1: the style says (XL), but BOX # says "XL & Mix" -> XL (the bracket wins).
     - **96 style codes are new to the WMS** (not in the data before 2026-11-24, Part 1 or 2): v1's 88 below (all still in v2) plus 8 new in v2.
       - **The 8 new in v2:** `EHPVC-001 1KS` (probably `EHPVC-001LKS`), VDAW-129, `VDAW-139 & 129`, VDLBB-019,
         `VDSB-2060 PNK`, `VDSB-2073 GRN`, `VDSB-2105 BLK`, VDZU-031.
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
     - **Box counts are not stored** (BOX # left empty on purpose: see the traps below). They are in `part2_v2_REPORT.txt`.
     - **1b / 0003:** 4 duplicate groups are still active (checked on `export_after_part2_v2.csv`). See decision 3, "Update 2026-11-24".
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
- [x] **1b access windows closed (2026-11-26):** TCP proxy removed and DB password regenerated again on **staging and production**.
- [x] **Pre-deploy step `alembic upgrade head` set** on the main service in **staging and production** (2026-11-26). Keep it.
- [ ] **Delete the `receiving-check-dev` service and the staging environment** when they are no longer needed (staging is still useful for the 1b-b rehearsal).
- [ ] **Rotate the production `INTERNAL_API_KEY` and the picking device tokens.** They appeared in screenshots.
- [ ] **Retire the old `nandu` / `manager` accounts.** Create the new personal admin account first.
- [ ] **Optional clean-up:** `railway.json` still contains a `startCommand` and `preDeployCommand` that nothing reads. Trim or remove it in a later commit.

## 4. Deploy order (when you decide to deploy, not before)

1. **1a via staging:** done 2026-11-21.
2. **1b-a via staging:** done 2026-11-26 (production at 0002).
3. **Next: 1b-b (0003):**
   - fresh Export CSV; re-check the Part 2 duplicate groups (decision 3);
   - deactivate the extra rows **in the app** (production; no SQL);
   - staging: deactivate its duplicates too, then point staging at `phase-1b-b` and check the log for `Running upgrade 0002 -> 0003`;
   - production: back up, open the 1b-b PR into `main`, merge (the Pre-deploy step is already set, so the merge deploy runs 0003);
   - if 0003 refuses (duplicates left), the deploy is aborted and 1b-a keeps running: nothing changes.

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
   git checkout phase-1b-b
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
   .venv\Scripts\python -m alembic upgrade head        # builds the empty schema in warehouse_dev
   ```
   - The new `warehouse_dev` is empty. The old PC's dev data (a copy of the inventory CSV) is not in git.
   - Load inventory only if you need it, with `scripts/migrate_inventory.py`. See the README.
6. **Run the checks:**
   ```powershell
   .venv\Scripts\ruff check .
   .venv\Scripts\python -m pytest -q                       # expect 69 passed (phase-1b-b)
   cd services\picking-service; ..\..\.venv\Scripts\python -m pytest -q; cd ..\..   # expect 9 passed
   ```

## 6. What to tell Claude Code on the new PC

Open Claude Code in the repo folder and paste:

> Read HANDOFF.md, WMS_Restructure_Prompt.md, docs/CHANGELOG.md and docs/DEPLOY_1B.md. We are on branch
> phase-1b-b. 1a and 1b-a are deployed (main = d9f1811, production at migration 0002). Do not deploy, do not push to main, and never run anything
> against the production database unless I explicitly say so in that message. First verify my new PC
> setup (section 5): .venv, .env pointing at a LOCAL database, warehouse_dev and warehouse_test exist,
> `alembic upgrade head`, ruff and both test suites pass. Report the results. Then wait for my
> decisions on the open items in section 2 before changing anything.
