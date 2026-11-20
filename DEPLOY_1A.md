# Deploying Phase 1a (emergency fixes)

Branch: `phase-1a-emergency-fixes`. **Do not deploy straight to production.** Deploy to a Railway
**staging** environment first, run the checklist in §5, then production.

Phase 1a changes **no database schema** and runs **no migrations**. Rollback = redeploy the previous
build (§7).

---

## 1. What changes for people on the floor

| Who | What they will notice |
|---|---|
| Everyone | Must be logged in. A session that expires sends them to the login page (and back afterwards). |
| Staff / Leads | Can look up stock, receive, and stage inbound shipments. **Cannot** adjust, edit, delete, export, or use `/manage`. |
| Manager | Same as today (lookup, `/manage`, receiving). Cannot approve inbound shipments or manage users. |
| Admin | Everything, including approving inbound shipments and user access. |
| New sign-ups | Always start as Floor Staff and must be approved. To give someone a higher role, the admin creates the account in the admin panel. |
| QR pickers | Each phone/scanner must enter a **device token once** (§3). Picks are logged with the device name. |
| Inbound (AI) | If Gemini is not configured or fails, staff see a clear error and enter lines by hand. No made-up lines, quantities or shelf locations. |
| Deleting rows | Rows with movement history can no longer be deleted. Bring them to 0 with "Adj" or by editing the row on `/manage`. |

---

## 2. Environment variables per Railway service

Legend: **R** = required, O = optional. "NEW" = did not exist before 1a.

### 2.1 `warehouse-management-system` (main app, gateway)

| Variable | | Value |
|---|---|---|
| `DATABASE_URL` | **R** | Railway reference to the Postgres plugin, e.g. `${{Postgres.DATABASE_URL}}`. The app now **refuses to start** without it (no SQLite fallback). `DATABASE_PUBLIC_URL` / `POSTGRES_URL` are still accepted as fallbacks, but set `DATABASE_URL` explicitly. |
| `INTERNAL_API_KEY` | **R** | Shared secret (§3.1). **Same value on all three services.** No default any more: if unset, QR picking and vision lookups stop working. |
| `PICKING_SERVICE_URL` | R* | Private URL of picking-service, e.g. `http://picking-service.railway.internal:<PORT>`. *If unset, the main app tries to start picking-service inside its own container, and that copy then needs `PICK_DEVICE_TOKENS` and `PUBLIC_BASE_URL` here too. Recommended: set it.* |
| `VISION_SERVICE_URL` | R* | Private URL of vision-llm-service, e.g. `http://vision-llm-service.railway.internal:<PORT>`. |
| `GEMINI_API_KEY` | O (NEW meaning) | Google AI Studio key. Without it the inbound "Extract with AI" button returns "AI reader not configured". |
| `GEMINI_MODEL` | O, **NEW** | Exact Gemini model ID to use (pick a current one in Google AI Studio). Required together with `GEMINI_API_KEY`; there is no default model. |
| `ALLOWED_ORIGINS` | O, **NEW** | Comma-separated list of *other* sites allowed to call the API from a browser, e.g. `https://alexander-warehouse.up.railway.app`. Leave **empty** if only the app's own pages are used (they are same-origin and need nothing). `*` is rejected. |
| `PORT` | — | Set by Railway. |

Remove if present (no longer read): `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SERVER_HOST`, `SERVER_PORT`.

### 2.2 `picking-service`

| Variable | | Value |
|---|---|---|
| `INVENTORY_SERVICE_URL` | **R** | Private URL of the main app, e.g. `http://warehouse-management-system.railway.internal:<PORT>`. |
| `INTERNAL_API_KEY` | **R** | Same value as the main app. **Service refuses to start without it.** |
| `PICK_DEVICE_TOKENS` | **R, NEW** | `name:token,name:token`, one entry per phone/scanner (§3.2). Tokens ≥ 24 chars, all different. **Service refuses to start without at least one.** |
| `PUBLIC_BASE_URL` | **R** (recommended) | Public site URL encoded into QR codes, e.g. `https://alexander-warehouse.up.railway.app`. Do not leave empty in production. |
| `MAX_PICK_QUANTITY` | O | Default 500. |

### 2.3 `vision-llm-service`

| Variable | | Value |
|---|---|---|
| `INVENTORY_SERVICE_URL` | **R** | Private URL of the main app. |
| `INTERNAL_API_KEY` | **R** | Same value as the main app. Without it, live location lookups are skipped and **train/feedback return 503**. |
| `MAX_IMAGE_BYTES` | O | Default 12 MB. |

---

## 3. Generating the secrets

Run on any computer with Python 3 (output is random each time; never reuse the examples):

```powershell
# 3.1 INTERNAL_API_KEY (one value, copy into all three services)
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3.2 One device token per picking phone/scanner
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Without Python (PowerShell only):

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 } | ForEach-Object { [byte]$_ })) -replace '[+/=]',''
```

Build `PICK_DEVICE_TOKENS` from short device names you will recognise in the audit trail:

```
PICK_DEVICE_TOKENS=line1-zebra:<token A>,line2-zebra:<token B>,maria-phone:<token C>
```

Keep a private list "device → token" (password manager). To **revoke** a lost device, delete its
entry and redeploy picking-service; the other devices keep working.

**Registering a device** (once per phone/scanner, after picking-service is deployed):
- Scan any section QR. The page shows "Register this device". Paste the token and tap **Save device token**.
- Or open once on that device: `https://<site>/pick/s/P1-L1-S1#device_token=<token>`. The part after `#` is never sent to the server.

---

## 4. Step order

1. **Back up production** (full, data included) and keep the file safe:
   `pg_dump --format=custom --file=prod_before_1a.dump "<DATABASE_PUBLIC_URL>"`
2. **Create a staging environment** in Railway (Project → Environments → New → duplicate production),
   with its **own** Postgres. Restore the backup into it:
   `pg_restore --no-owner --dbname "<STAGING DATABASE_PUBLIC_URL>" prod_before_1a.dump`
3. In **staging**, set all variables from §2 (use *different* secrets than production), point all three
   services at the `phase-1a-emergency-fixes` branch, deploy, and run the **checklist in §5**.
4. Fix anything that fails on staging (new commits on the branch), redeploy staging, and re-run §5.
5. **Production, variables first.** Use Railway's *staged changes* so all variables apply at once:
   set `INTERNAL_API_KEY` (all 3), `PICK_DEVICE_TOKENS` + `PUBLIC_BASE_URL` (picking),
   `GEMINI_API_KEY` + `GEMINI_MODEL`, `ALLOWED_ORIGINS` (main). Do **not** deploy yet.
6. **Merge the PR** into `main` and deploy production in this order:
   1. `warehouse-management-system` (main app). Watch the logs for `[Database] N inventory records present.` It must show the **same** count as before. No "Seeding" or "Backfilling" lines should appear.
   2. `picking-service`. Its health check `/pick/health` must return `auth_required: "device_token"`.
   3. `vision-llm-service`.
7. **Register every picking phone/scanner** (§3) before the next shift starts.
8. **Change the passwords of the old built-in accounts** (they were in source code):
   - `nandu`: from a computer with the repo, run
     `python scripts/create_admin.py nandu "Nandu (Admin)"` with `DATABASE_URL` pointing at production.
     It prompts for the new password (min 12 characters) and logs out existing sessions.
   - `manager`: there is no password-change screen yet. If nobody uses this shared account,
     **Revoke** or **Delete** it in the admin panel. If it is in use, create personal Manager accounts
     in the admin panel and then revoke `manager`. (Do **not** use `create_admin.py` for it; that script
     makes the account an ADMIN.)
9. Run the **production smoke test** (the ★ items in §5) and keep watching the logs for an hour.

---

## 5. Staging test checklist

Use four browser profiles (or private windows): **Admin**, **Manager**, **Staff**, **Logged out**.
Items marked ★ are also the production smoke test.

### Startup and data safety
- [ ] ★ Main app log shows `[Database] N inventory records present.` with the same N as production before the deploy.
- [ ] No log lines about "Seeding … Line 14", "Backfilling", or "Auto-seeding".
- [ ] Remove `DATABASE_URL` in staging and redeploy: the app **fails to start** with "DATABASE_URL is not set". Put it back.

### Login and roles
- [ ] ★ Logged out: opening `/` goes to `/login`. `https://<site>/api/stats` returns **401**.
- [ ] Logged out: `https://<site>/api/export-csv` returns **401** (no CSV download).
- [ ] ★ Staff: dashboard lookup works (search a style, Line 14, a Row). Map works.
- [ ] Staff: no Adj/delete buttons; opening `/manage` redirects to `/`.
- [ ] Manager: `/manage` works: search locations, edit a row and Save, CSV export downloads.
- [ ] Manager: approving an inbound shipment fails with "Admin access required".
- [ ] ★ Admin: user-access panel lists users. Approve and revoke a test account.
- [ ] Leave a page open, log out in another tab, then click something on the first page: you land on `/login` and return after logging in.

### Sign-up
- [ ] Sign-up form has **no Role field**. Create a test account: the message says it needs approval.
- [ ] Logging in with it before approval shows "pending approval".
- [ ] Admin panel shows it as role **STAFF**, Pending. Approve it: login now works, as Staff.

### Stock changes and history
- [ ] Admin: "Adj" −1 on a test row. Movements/Audit shows the change with **the admin's real name** (not "Manager").
- [ ] Manager on `/manage`: edit a test row's quantity and Save. Audit shows the manager's real name.
- [ ] Try to delete a row that has history: a red message explains it can't be deleted and names "Adj" / "edit and Save". The row is still there.
- [ ] Bring that row to 0 with "Adj". The audit shows the deduction. The row still exists with 0 pcs.
- [ ] Bulk-delete on `/manage` with one row that has history selected: "Nothing was deleted…", and nothing is deleted.
- [ ] Delete a brand-new row with no history (create one with "Add location" and **quantity 0**; a quantity above 0 records a movement immediately): works.

### Inbound / AI reader
- [ ] With `GEMINI_*` **unset**: "Extract with AI" shows "AI document reader is not configured…". No lines appear.
- [ ] With `GEMINI_*` set: a real packing-list photo produces lines whose shelf location is **Unassigned** and whose numbers come only from the document.
- [ ] "+ Add Item Line" adds a **completely empty** line (no A12501, no 60 pcs, no Line 1 location).
- [ ] Submitting a line with an empty style shows "Line #n: style is required."
- [ ] Admin approves a test shipment: stock appears at the locations that were entered.

### QR picking
- [ ] ★ `/pick/health` shows `"auth_required": "device_token"`.
- [ ] On a phone with no token, scanning a section QR shows "Register this device". Stock is not shown.
- [ ] A wrong token is rejected and the page asks again.
- [ ] ★ With a valid token: the station shows stock. Pick 1 piece: success. Audit shows `… [device-name]`.
- [ ] `/pick/labels`, a single label page, and `/pick/labels.pdf?line=1` still open **without** a token. Printed QR URLs use `PUBLIC_BASE_URL`.
- [ ] Remove a device from `PICK_DEVICE_TOKENS` and redeploy: that phone is asked to register again.

### Vision / scan
- [ ] `/scan` analyzes a photo (still public).
- [ ] Logged out or Staff: "Retrain" / "Save correction" fails with "Admin or Manager login required".
- [ ] Manager/Admin: "Retrain" works.

### Security spot checks
- [ ] Create a test style named `<img src=x onerror=alert(1)>` on staging (Add location, quantity 0). Search for it on the dashboard and `/manage`: the text shows literally and **no alert pops up**. Then delete it.
- [ ] `curl -H "X-Internal-Key: wh-internal-default-key-2026" https://<site>/api/internal/catalog` returns **403**.
- [ ] `curl -H "Origin: https://evil.example" -I https://<site>/api/health` has **no** `access-control-allow-origin` header.

---

## 6. Known limits after 1a (planned for 1b and later)

- The database still has `ON DELETE CASCADE` from `stock_movements` to `inventory_items`. Deletes are blocked in code; the first Alembic migration removes the cascade and adds a real "deactivate" flag.
- Style rename (`/manage`) still rewrites the style name on past movement rows.
- Sheet-submit, receiving and shipment approval still record the typed name, not the logged-in user.
- There is no password-change screen.
- `/scan/api/analyze` and the label pages are public by design.

## 7. Rollback

Railway → service → Deployments → previous deployment → **Redeploy**, for each service in reverse
order (vision, picking, main). 1a made no schema or data changes, so no database restore is needed.
New variables can stay; the old code ignores them, **except** that old code falls back to the
public default `INTERNAL_API_KEY` only when the variable is unset. Keep it set.
