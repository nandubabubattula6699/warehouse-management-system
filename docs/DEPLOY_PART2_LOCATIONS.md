# Deploying Part 2 locations (migration 0004, steps C, D0–D3, E)

**Status: not deployed.** Branch `feature/part2-locations`. Staging first, then production. Every production step needs
the owner's explicit OK. Allbirds (Part 1, Lines) is not changed by any step: the database refuses a location link on
an Allbirds row.

## What it adds

| Part | What |
|---|---|
| Migration `0004` | `locations` (Part 2 spots), `location_changes` (append-only record), empty `inventory_items.location_id`. No row changes. Runs through the dashboard **Pre-deploy step** (`alembic upgrade head`), already set on both environments. |
| `/locations` (admin) | 1–3: import the row-size workbook (preview → apply). Print labels. 4 (D0): deactivate empty Part 2 rows. 5 (D1/D2): match report → link stock to spots. |
| `/loc` (any login) | Scan or type a location: QR link, Code 128 code or typed code. Read only. |
| D3 | Every Part 2 create / edit / sheet IN-SET / receiving / inbound approval / reactivate resolves its spot. With `PART2_LOCATIONS_ENFORCED=1` a spot that is not an active location is refused (409, nothing saved). |
| New dependency | `openpyxl` (installed by the normal build). |

## Variables

| Variable | Staging | Production |
|---|---|---|
| `LOCATION_LABEL_BASE_URL` | **Set it to the staging address** (e.g. `https://<staging>.up.railway.app`), so QR codes printed from staging open staging. | Leave unset: the default is `https://alexander-warehouse.up.railway.app`. |
| `LOCATION_LABEL_SIZE` | unset (4x6) | unset (4x6); `4x2` for the compact label |
| `LOCATION_LABEL_QR` | unset (link ending with the code) | unset |
| `PART2_LOCATIONS_ENFORCED` | **unset until D2 is done**, then `1` | **unset until D2 is done**, then `1` |

`PART2_LOCATIONS_ENFORCED` must stay off until the locations exist and the stock is linked: before that, every Part 2
write would be refused. While it is off, writes still link to the spot automatically when the spot exists.

## Staging

1. **Bring staging to `main`.** Staging runs `phase-1b-a` (0002) with older data (2026-11-21) and its own Part 2
   duplicates. Deactivate those duplicates in the app first (0003 refuses otherwise), then switch the staging branch to
   `main` and check the log for `Running upgrade 0002 -> 0003`.
2. **Set `LOCATION_LABEL_BASE_URL`** to the staging address. Leave `PART2_LOCATIONS_ENFORCED` unset.
3. **Switch the staging branch to `feature/part2-locations`.** Log: `Running upgrade 0003 -> 0004`, then
   `Schema at migration 0004`.
4. `/locations`: import `C:\WMS-backups\part2_row_sizes_2026-11-26.xlsx` (preview: 1,377 spots, no problems) → apply.
5. Print one row of labels on the Zebra at 100 %. Scan one with a phone (QR opens staging `/loc/...`) and one with a
   scanner gun into `/loc`.
6. Step 4 (D0) preview → apply; step 5 match report → link. Staging data is older, so this tests the mechanics only.
7. Set `PART2_LOCATIONS_ENFORCED=1`, redeploy. Try a sheet IN to a spot that does not exist: 409, nothing saved.

## Production (each step with the owner's OK)

1. **Backup** (`pg_dump -Fc`, as in `DEPLOY_1B.md`, through a short access window) and an audit export.
2. Open the PR `feature/part2-locations` → `main`, wait for green CI, merge. The Pre-deploy step runs 0004.
   Log: `Running upgrade 0003 -> 0004`, `Schema at migration 0004`. Dashboard totals unchanged.
3. `/locations`: import the final workbook (1,377 spots) → apply. Every spot is recorded in `location_changes`.
4. Print one row; check it on the floor (phone and scanner gun). Then print the rest.
5. D0: preview, review both lists (tick only the empty rows at existing spots that should go), apply.
6. D1: match report and CSV for the owner. Expected: rows with stock 1,549 / 54,858 pcs will be linked, 0 with stock
   unmatched. **D2 only after the owner's OK.** Check afterwards: linked rows and pieces equal the report.
7. Set `PART2_LOCATIONS_ENFORCED=1` and redeploy. Check a sheet IN to a missing spot is refused.

## Undo

- Before D2: redeploy the previous version; `0004` can be downgraded (it refuses while any row is linked).
- After D2: links are recorded (`LOCATION_LINK` movements). Turning enforcement off (`PART2_LOCATIONS_ENFORCED` unset)
  restores the old write behaviour without touching data. Removing links needs a reviewed, recorded step; never SQL.
- Locations are never deleted: re-import a corrected workbook to deactivate or reactivate spots.
