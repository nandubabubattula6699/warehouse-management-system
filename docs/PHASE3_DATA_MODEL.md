# Phase 3–5 data model (design, needs approval)

Status: **design only.** Nothing here is built yet: no tables, no migrations, no code.
Input: branch `draft/wms-models-v2` (read, not merged), `docs/TARGET_ARCHITECTURE.md` (Phase 0), the current
schema (migrations 0001–0003), `CLAUDE.md` and the sample packing list `CI2025VD003`.

**Hard rule:** Part 1 (Allbirds, Lines) data is not changed by anything in this document (CLAUDE.md rule 7).

---

## 1. Summary

- **New tables live next to the old ones.** `inventory_items`, `stock_movements` and the other existing tables
  stay exactly as they are. Part 1 (Allbirds) keeps running on them.
- **Part 2 (VD, VO, ED) moves to the new model through the relocation and fresh count** that is already planned
  (HANDOFF decision 2). The fresh count becomes the opening balance of the new ledger. Old Part 2 rows are
  deactivated in the app (recorded, history kept), not converted. So no messy legacy Part 2 data has to be migrated.
- **Inventory is a ledger.** `inventory_transactions` is append-only (enforced by the database, not only by code).
  `inventory_balances` is maintained by the database in the same transaction and can always be rebuilt from the ledger.
- **Receiving flow (Part 2 only):** packing list import → inbound order → one receipt per truck → blind carton
  scanning with pre-printed LPNs → compare at Finish → holds / damage / manager approval → directed put-away.
  Allbirds (Part 1) keeps its current receiving exactly as it is.
- **Every write records who and when.** The database refuses writes that have no user attached.

---

## 2. Conventions (all new tables)

| Topic | Rule |
|---|---|
| Table names | Plural, snake_case, like the existing tables (`inventory_items`, `stock_movements`). |
| Primary keys | `id bigint GENERATED ALWAYS AS IDENTITY`. |
| Time | `timestamptz`, stored in UTC, default `now()` from the database (not from the app server or phone). |
| Who | `created_by bigint NOT NULL REFERENCES warehouse_users(id)`. Mutable tables also have `updated_at`, `updated_by`, `row_version int`. A `SYSTEM` user row is used for automatic jobs. |
| Status columns | `text` + `CHECK (status IN (...))`. Easier to extend in a migration than a Postgres enum. |
| Codes | Stored upper-case and trimmed. `CHECK (code = upper(btrim(code)))`. |
| Quantities | `integer`. `CHECK (qty > 0)` on documents (lines, cartons); the ledger allows negative (outbound legs) but never 0. |
| Foreign keys | Always `ON DELETE RESTRICT` (the default). No cascades on business data. Every FK column has an index. |
| Deleting | Business rows are never deleted. They get a status (`VOID`, `CANCELLED`, `is_active = false`) with who/when/why. |
| Schema changes | Alembic only (CLAUDE.md rule 6). Every migration reversible. |
| Postgres version | 15 or newer (uses `UNIQUE NULLS NOT DISTINCT`). Production version is checked during the 1b schema check (pg_dump 18 worked against it on 2026-11-21). Fallbacks are kept for older versions and missing extensions (§5.1, §5.5). |
| Settings | Business thresholds live in `app_settings` (§3.10), never hard-coded. |

---

## 3. Tables

Legend: **PK** primary key, **FK** foreign key, **UQ** unique, **CK** check constraint.
"Audit columns" = `created_at`, `created_by` (+ `updated_at`, `updated_by`, `row_version` where the row can change).

### 3.1 Master data (catalog)

**`brands`**
| Column | Notes |
|---|---|
| `code` | UQ. `VD`, `VO`, `ED`. |
| `name` | UQ. VON DUTCH, VALENTINO ORLANDI, ED HARDY. |
| `warehouse_part` | CK `IN ('PART_1','PART_2')`. All three are PART_2. Allbirds is not in the new catalog (Part 1 stays on the old tables). |

**`styles`** (draft: `products`)
| Column | Notes |
|---|---|
| `brand_id` | FK brands. |
| `code` | UQ (global, not per brand: a scanned or typed style must resolve to one style). e.g. `VDP-2056GLD`, `VOMCB-001`. |
| `description`, `is_active` | |
| `created_via_import_id` | FK `inbound_order_imports`, null if created elsewhere. Shows which packing list introduced the style. |

New styles, colors and sizes arrive all the time. A **manager can create them directly from the import screen**
(§3.3), not only map to existing ones. Creation is recorded like any other write (`created_by`, `created_at`,
`created_via_import_id`, plus an `audit_log` row).

**`colors`**
| Column | Notes |
|---|---|
| `code` | UQ. Our own color name, e.g. `BLACK`, `GOLD GLITTER`, `LEOPARD/BLACK`. `STANDARD` exists for items without a color. |
| `created_via_import_id` | As for styles. |

**`sizes`**
| Column | Notes |
|---|---|
| `scale` | e.g. `ONE SIZE` (bags), `ALPHA` (apparel XS–XL), `NUMERIC` (7, 8, 9, 10). |
| `label` | e.g. `OS`, `M`, `10`. UQ `(scale, label)`. |
| `sort_order` | For display order (XS < S < M < L < XL; 7 < 8 < 9 < 10). |
| `created_via_import_id` | As for styles. |

**`skus`**: one row per style + color + size.
| Column | Notes |
|---|---|
| `style_id`, `color_id`, `size_id` | FKs. UQ `(style_id, color_id, size_id)`. Also UQ `(id, style_id, color_id)` so other tables can check that a SKU belongs to a given style + color (§3.3). |
| `default_pcs_per_carton` | Optional. CK `> 0`. |
| `status` | CK `IN ('ACTIVE','DISCONTINUED')`. |

**`sku_barcodes`**: UPC/EAN and other scannable codes.
| Column | Notes |
|---|---|
| `barcode` | UQ (one barcode = one SKU, forever). |
| `sku_id` | FK skus (RESTRICT, the draft had CASCADE). |
| `barcode_type` | CK `IN ('UPC_A','EAN13','GTIN14','VENDOR')`. |

### 3.2 Suppliers and import profiles

**`suppliers`**: `code` UQ, `name`, `is_active`.

**`supplier_import_profiles`**: how to read one supplier's packing-list Excel. Versioned; a profile that has been
used is never edited, a new version is created instead (so old imports can still be explained).
| Column | Notes |
|---|---|
| `supplier_id`, `version` | UQ `(supplier_id, version)`. |
| `sheet_name` | e.g. `PL`. |
| `header_anchor` | Text that must be found in the header, e.g. `STYLE`. Import fails if it is not where expected. |
| `header_first_row`, `header_row_count` | e.g. 10 and 2 (header spread over 2 rows). |
| `data_first_row` | e.g. 12. |
| `column_map` | `jsonb`: our field → supplier column, e.g. `{"style":"D","color":"E","pcs_per_carton":"F","carton_count":"G","qty":"H","carton_from":"A","carton_to":"B"}`. CK: required keys present. |
| `totals_row_marker` | e.g. `TOTAL` (first column). Reading stops there; the row's numbers become the declared totals. |
| `invoice_no_cell`, `ship_date_cell` | e.g. `G4`, `I4`. |
| `date_mode` | CK `IN ('EXCEL_SERIAL','DATE','TEXT')`. Excel date numbers (e.g. 46177) are converted with the 1900 date system. |
| `carton_numbering` | CK `IN ('RESTART_PER_LINE','CONTINUOUS')`. |
| `size_mode` | CK `IN ('NONE','COLUMN','GRID')`. **NONE**: no size column, every line gets `default_size` (the sample). **COLUMN**: one row per style/color/size, size in `column_map.size`. **GRID**: one row per style/color with one quantity column per size. |
| `default_size` | e.g. `OS`. CK: required when `size_mode = 'NONE'`. |
| `size_grid_columns` | `jsonb`, GRID only: supplier column → size label, e.g. `{"H":"S","I":"M","J":"L","K":"XL"}`. CK: required when `size_mode = 'GRID'`. |
| `grid_values_are` | GRID only. CK `IN ('PER_CARTON','LINE_TOTAL')`: whether the size quantities are per carton (prepack breakdown) or the total for the line. For `LINE_TOTAL` the per-carton breakdown is total ÷ cartons; if it doesn't divide evenly, the import raises `SIZE_BREAKDOWN_UNCLEAR` (§3.3). |
| `is_active` | Only one active version per supplier: partial UQ `(supplier_id) WHERE is_active`. |

**`supplier_style_aliases`**: supplier text → our style (fixes typos like `VDP-VDP-2057` → `VDP-2057` once, reused next time).
UQ `(supplier_id, alias)`. `style_id` FK. Audit columns.

**`supplier_color_aliases`**: supplier color text → our color, e.g. `leo with black` → `LEOPARD/BLACK`.
| Column | Notes |
|---|---|
| `supplier_id`, `alias` | Alias stored normalized (upper, single spaces). |
| `style_id` | Optional: an alias can be valid for one style only. UQ `NULLS NOT DISTINCT (supplier_id, style_id, alias)`. |
| `color_id` | FK colors. |

**`file_uploads`**: every imported file is kept.
`filename`, `content_type`, `size_bytes`, `sha256` (64 hex), `storage_key` (object storage / volume path), audit columns.
Index on `sha256` so a re-upload of the same file is detected and shown ("already imported as order IO-…").

### 3.3 Inbound orders (packing list = expected goods)

**`inbound_orders`**: one per packing list / commercial invoice.
| Column | Notes |
|---|---|
| `order_no` | UQ, generated by the WMS (e.g. `IO-2026-00017`). |
| `supplier_id` | FK. |
| `invoice_no` | Supplier invoice number. Partial UQ `(supplier_id, invoice_no) WHERE invoice_no IS NOT NULL`: the same invoice can't be imported twice. May be empty while receiving (the truck may arrive first). CK: `status IN ('CLOSED','CLOSED_SHORT')` ⇒ `invoice_no IS NOT NULL`. |
| `ship_date`, `ship_mode`, `origin`, `destination`, `is_ddp` | From the file header. |
| `declared_cartons`, `declared_units` | From the file's TOTAL row (sample: 466 / 22,624). Kept as declared; never recalculated. |
| `status` | CK `IN ('DRAFT','OPEN','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CLOSED_SHORT','CANCELLED')`. |
| `closed_by`, `closed_at`, `close_reason` | CK: `CLOSED_SHORT` and `CANCELLED` require `close_reason` and `closed_by`. |
| Audit columns + `row_version` | |

**`inbound_order_imports`**: one per import attempt (a file can be fixed and re-imported).
`inbound_order_id` FK, `file_upload_id` FK, `profile_id` FK, `status` CK `IN ('VALIDATING','HAS_ERRORS','ACCEPTED','REJECTED')`,
`computed_cartons`, `computed_units`, audit columns.

**`inbound_import_issues`**: what the validator found. An import can only be ACCEPTED when no `ERROR` is unresolved.
| Column | Notes |
|---|---|
| `import_id`, `source_row` | Excel row number, so a person can find it in the file. |
| `severity` | CK `IN ('ERROR','WARNING')`. |
| `code` | CK `IN ('UNKNOWN_STYLE','UNKNOWN_COLOR','UNKNOWN_SIZE','TOTAL_MISMATCH','MISSING_INVOICE_NO','BAD_DATE','BAD_NUMBER','QTY_NOT_PACK_X_CARTONS','SIZE_BREAKDOWN_UNCLEAR','CARTON_RANGE_GAP','DUPLICATE_LINE','UNEXPECTED_LAYOUT')`. `MISSING_INVOICE_NO` and `QTY_NOT_PACK_X_CARTONS` are WARNINGs; the unknown-value codes are ERRORs. |
| `raw_value`, `message` | Exactly what was in the cell. Nothing is guessed (CLAUDE.md rule 5). |
| `resolution_type` | CK `IN ('MAPPED_EXISTING','MAPPED_AND_ALIAS_SAVED','CREATED_NEW','ACKNOWLEDGED')`. `CREATED_NEW` = the manager created a new style/color/size from the import screen. `ACKNOWLEDGED` is only allowed for WARNINGs. |
| `created_style_id`, `created_color_id`, `created_size_id` | Set when `resolution_type = 'CREATED_NEW'` (CK: exactly one of them). |
| `resolution_note`, `resolved_by`, `resolved_at` | e.g. "mapped to VDP-2057, alias saved". CK: resolved ⇒ both who and when. Resolving needs the manager role. |

**`inbound_order_lines`**: one line = one style + color packed the same way in `carton_count` cartons.
| Column | Notes |
|---|---|
| `inbound_order_id`, `line_no` | UQ `(inbound_order_id, line_no)`. |
| `source_row` | Excel row. |
| `supplier_style_text`, `supplier_color_text` | Exactly as in the file (audit trail for aliases). |
| `style_id`, `color_id` | FKs. NOT NULL: a line only exists once style and color are resolved (mapped or newly created). |
| `pcs_per_carton`, `carton_count`, `expected_qty` | CK each `> 0`. `pcs_per_carton` = all sizes together (e.g. a 1S/2M/2L/1XL prepack = 6). |
| `carton_from`, `carton_to` | Supplier's carton numbers (restart per line in the sample). CK `carton_to >= carton_from`. |
| `net_kg`, `gross_kg`, `carton_dims_cm`, `cbm` | Optional, informational. |

**`inbound_order_line_sizes`**: the size breakdown of a line, **per carton**. Every line has at least one row:
a one-size line has exactly one (e.g. OS × 40); a prepack has one row per size (S 1, M 2, L 2, XL 1).
| Column | Notes |
|---|---|
| `line_id`, `sku_id` | UQ `(line_id, sku_id)`. |
| `style_id`, `color_id` | Copied from the line. Composite FK `(sku_id, style_id, color_id)` → `skus (id, style_id, color_id)` and `(line_id, style_id, color_id)` → `inbound_order_lines`, so a size row can never point at another style or color. |
| `pcs_per_carton` | CK `> 0`. |
| `expected_qty` | CK `> 0`. Normally `pcs_per_carton × carton_count`. |
| `received_qty`, `damaged_qty` | Maintained when receipts are approved (cache; can be recomputed from receipts). CK `>= 0`. |

Checks done by the importer as **warnings** (decided: not DB constraints, because suppliers sometimes ship one short
carton): `expected_qty = pcs_per_carton × carton_count`, and the size rows add up to the line's `pcs_per_carton`.
Receiving compares per SKU (size), so a prepack carton with the wrong size mix shows up as a variance.

### 3.4 Receipts (one per truck / delivery)

**`receipts`**
| Column | Notes |
|---|---|
| `receipt_no` | UQ, generated (e.g. `RC-2026-00041`). |
| `inbound_order_id` | FK. Several receipts per order (partial / DDP deliveries). |
| `bol_no`, `carrier`, `trailer_no`, `seal_no` | UQ `(inbound_order_id, bol_no)`. |
| `bol_carton_count` | Cartons stated on the BOL. CK `> 0`. |
| `arrived_at` | |
| `damage_notes` | Free text at the dock (plus photos via `file_uploads`, see `receipt_files`). |
| `status` | CK `IN ('OPEN','FINISHED','APPROVED','CANCELLED')`. |
| `finished_by/at`, `approved_by/at` | CK: status ⇒ matching who/when present. |
| Audit columns + `row_version` | |

**`receipt_files`**: photos and BOL scans: `receipt_id`, `file_upload_id`, `kind` CK `IN ('BOL','DAMAGE_PHOTO','OTHER')`.

**`receipt_cartons`**: one row per scanned LPN.
| Column | Notes |
|---|---|
| `receipt_id` | FK. |
| `lpn_id` | FK lpns. **UQ** (an LPN can be received once, ever). |
| `condition` | CK `IN ('OK','DAMAGED')`. |
| `copied_from_id` | FK to the previous carton when "same as last" was used (contents copied, LPN still scanned). |
| `voided_at`, `voided_by`, `void_reason` | A wrong scan is voided, not deleted. CK: all three or none. The LPN is **burned** (status `VOID`, never usable again); the worker puts a new label on the carton and scans that. |
| `scanned_by`, `scanned_at`, `device_name` | |

**`receipt_carton_lines`**: what is in the carton (one SKU, or several for a mixed-size prepack carton).
`receipt_carton_id` FK, `sku_id` FK, `qty` CK `> 0`, UQ `(receipt_carton_id, sku_id)`.

**`receipt_variances`**: created at **Finish** by comparing what was scanned with what was expected.
| Column | Notes |
|---|---|
| `receipt_id`, `inbound_order_line_size_id` (null for an unexpected SKU), `sku_id` | |
| `type` | CK `IN ('OVER','SHORT_CARTONS_VS_BOL','UNEXPECTED_SKU','DAMAGED','PACK_SIZE_DIFFERENT')`. |
| `expected_qty`, `received_qty` | |
| `status` | CK `IN ('OPEN','ACCEPTED','REJECTED')`. Only a supervisor can decide. Nothing is auto-accepted (CLAUDE.md rule 4). |
| `decided_by`, `decided_at`, `decision_note` | CK: decided ⇒ all three. |

**Over-receipt is always a variance** for a supervisor, with no tolerance: as soon as the received total for a SKU on the
order (all receipts so far) is above `expected_qty`, Finish creates an `OVER` variance.
**Shortages per line** are not final at Finish when more trucks are coming. They are evaluated when the order is
closed: either `CLOSED` (everything arrived) or `CLOSED_SHORT` by a manager with a reason.

### 3.5 LPNs (pre-printed carton labels)

**`lpn_label_batches`**: a range the WMS issues for BarTender to print.
| Column | Notes |
|---|---|
| `prefix` | e.g. `L`. |
| `first_no`, `last_no` | CK `last_no >= first_no`, CK `last_no - first_no < 5000` (sane batch size). |
| Overlap guard | `EXCLUDE USING gist (prefix WITH =, int8range(first_no, last_no, '[]') WITH &&)`. Two batches can never contain the same number. Needs the `btree_gist` extension (fallback in §5.1). |
| `bartender_file_id` | FK file_uploads (the CSV sent to BarTender). |
| `printed_at`, `printed_by` | |

**`lpn_counters`**: one row per prefix with `next_no`. Issuing a batch locks this row (`SELECT … FOR UPDATE`), so two
managers issuing at the same time get different ranges.

**`lpns`**: one row per printed label, created when the batch is issued.
| Column | Notes |
|---|---|
| `code` | UQ forever, e.g. `L00012345` + check digit. The format cannot be confused with a location (`R3-S5-2`) or a UPC (12 digits). |
| `batch_id` | FK. |
| `status` | CK `IN ('ISSUED','RECEIVED','STORED','HOLD','EMPTY','VOID')`. |
| `current_location_id` | FK locations, null while ISSUED. |
| Status guard | Trigger: status can never go back to `ISSUED`; `EMPTY` and `VOID` are final. Rows can't be deleted. A voided scan sets the LPN to `VOID` (burned). |
| Stock per LPN | Stock stays tracked per LPN after put-away (decided). Picking pieces from a carton lowers that LPN's balance; when it reaches 0 the LPN becomes `EMPTY`, never reused. |

### 3.6 Locations

**`zones`**: `code` UQ (`PART_1`, `PART_2`, `DOCK`), `name`.

**`locations`** (draft: `bins`)
| Column | Notes |
|---|---|
| `code` | UQ. See the code scheme below. |
| `zone_id` | FK. |
| `location_type` | CK `IN ('STORAGE','RECEIVING','STAGING','DAMAGE')`. |
| `area` | STORAGE only. CK `IN ('ROW','WALL')`. |
| `row_no`, `section_no`, `level_no` | Integers for storage locations. `level_no` 0 = floor, 1–4 = shelf levels. `row_no` is null for WALL. |
| Code check | CK: ROW ⇒ `code = 'R'||row_no||'-S'||section_no||'-'||level_no`; WALL ⇒ `row_no IS NULL AND code = 'W-S'||section_no||'-'||level_no`; non-storage types ⇒ all coordinates null. So the code can never disagree with its coordinates. |
| `putaway_sequence` | Walking order, used for "nearest first" (§3.8). |
| `max_cartons` | Optional, **not used for now** (capacity is unknown). Kept so a capacity check can be added later without a schema change. |
| `is_active` | Deactivated, never deleted. |

Proposed code scheme (final names are set when the Part 2 layout is collected):

| Spot | Code | Coordinates |
|---|---|---|
| Shelf in a row | `R3-S5-2` | row 3, section 5, level 2 |
| Floor at a section (old GROUND_FRONT / GROUND_BACK) | `R3-S5-0` | level 0 = floor |
| Wall | `W-S12-1` (floor at the wall: `W-S12-0`) | no row, section 12, level 1 |
| Receiving / staging / damage | `R-RECV`, `R-STAGE`, `R-DAMAGE` | none |

If a section really has two separate floor spots (front and back), they need two codes. That is decided when the
layout is collected (§6, still open).

Part 1 (Lines) locations are **not** created in Phase 3 (Part 1 stays on the old tables).

### 3.7 Inventory (ledger and balances)

**`inventory_transactions`**: the ledger. **Append-only.**
| Column | Notes |
|---|---|
| `txn_group_id` | `uuid`. All rows of one business action (e.g. the − and + legs of a move) share it. |
| `txn_type` | CK `IN ('OPENING','RECEIVE','MOVE','ADJUST','COUNT','PICK','SHIP','DAMAGE')`. |
| `sku_id`, `location_id`, `lpn_id` (nullable) | FKs. |
| `qty` | Signed. CK `qty <> 0`. |
| `balance_after` | Filled by the database trigger under the balance row lock (so it is exact even with many phones). |
| `reason_code_id`, `reason_note` | CK: `ADJUST`, `COUNT` and `DAMAGE` require a reason code. |
| `receipt_id`, `adjustment_id`, `putaway_task_id`, `count_id` | Explicit nullable FKs to the document that caused it (instead of a loose `ref_type/ref_id` text pair, so the FK is checked). |
| `legacy_item_id` | For the Part 2 opening balances: which old `inventory_items` row it replaces (traceability). |
| `created_by`, `created_at`, `device_name` | NOT NULL (device optional). |

Ledger protection (database level, not just code):
1. `BEFORE UPDATE OR DELETE` trigger → raises an error. `BEFORE TRUNCATE` trigger → raises an error.
2. **Phase 4:** the app connects as a separate role (`wms_app`) without `UPDATE`/`DELETE`/`TRUNCATE` rights on this
   table; migrations keep running as the owner. Until then, the triggers in point 1 protect the ledger from day one.
3. Corrections are new rows (e.g. an `ADJUST` with a reason), never edits.

**`inventory_balances`**: current stock, a cache of the ledger.
| Column | Notes |
|---|---|
| `sku_id`, `location_id`, `lpn_id` | UQ `NULLS NOT DISTINCT (sku_id, location_id, lpn_id)`: loose stock (no LPN) and carton stock each have exactly one row. |
| `qty_on_hand` | CK `>= 0`. A movement that would make stock negative fails and nothing is saved. |
| `qty_allocated` | CK `>= 0 AND qty_allocated <= qty_on_hand` (Phase 6). |
| `updated_at`, `last_txn_id` | |

How the balance stays correct: a `BEFORE INSERT` trigger on `inventory_transactions` does
`INSERT … ON CONFLICT (sku_id, location_id, lpn_id) DO UPDATE SET qty_on_hand = qty_on_hand + NEW.qty` and
writes `balance_after`. Balance and ledger row are in the same transaction: both are saved, or neither.
Direct `INSERT/UPDATE/DELETE` on `inventory_balances` from anywhere else is refused by a trigger. A nightly job checks
`qty_on_hand = Σ ledger qty` for every row and flags any difference (Phase 4).

**`reason_codes`**: `category` CK `IN ('ADJUST','COUNT','DAMAGE','CLOSE_SHORT','PUTAWAY_OVERRIDE')`, `code`
(UQ `(category, code)`, e.g. `DAMAGED`, `FOUND`, `MISCOUNT`, `SUPPLIER_SHORT`; for put-away overrides a short list such
as `LOCATION_FULL`, `CLOSER_SPOT`, `SAME_STYLE_NEARBY`, `OTHER`), `description`, `is_active`.

**`inventory_adjustments`**: a manual adjustment request (CLAUDE.md rule 2).
| Column | Notes |
|---|---|
| `sku_id`, `location_id`, `lpn_id`, `qty` (signed, `<> 0`) | |
| `reason_code_id`, `note` | NOT NULL. |
| `status` | CK `IN ('PENDING_APPROVAL','APPROVED','REJECTED','POSTED')`. |
| `approval_limit_applied` | The limit in pieces that was used for this request (stored for the audit trail, because the setting can change later). |
| `approved_by`, `approved_at` | CK: approver ≠ requester. |
| Rule | Supervisor approval is needed when `abs(qty)` is **more than the smaller of** 50 pieces or one full carton (`pcs_per_carton` of that LPN/SKU). If the carton size is unknown, the 50-piece limit applies. Both numbers come from `app_settings` (§3.10), not from code. Below the limit the adjustment posts immediately (still with reason, who and when). Only `POSTED` creates ledger rows. |

**`inventory_holds`**: stock that may not be put away or picked.
`lpn_id` (or `receipt_variance_id`), `reason`, `placed_by/at`, `released_by/at`, `release_note`.
Partial UQ `(lpn_id) WHERE released_at IS NULL`: one open hold per LPN.

### 3.8 Put-away

**`putaway_tasks`**
| Column | Notes |
|---|---|
| `lpn_id` | FK. Partial UQ `(lpn_id) WHERE status = 'OPEN'`: one open task per carton. |
| `from_location_id`, `suggested_location_id`, `actual_location_id` | |
| `status` | CK `IN ('OPEN','DONE','CANCELLED')`. |
| `override_reason_id` | Optional, FK `reason_codes` (category `PUTAWAY_OVERRIDE`). |
| `was_overridden` | Generated column: `actual_location_id <> suggested_location_id`. Lets supervisors see how often suggestions are ignored. |
| `assigned_to`, `completed_by`, `completed_at` | |

**Suggestion rule** (no fixed rows per brand; stock goes wherever there is space):
1. a location that already holds the same SKU (balance > 0), nearest first;
2. otherwise an **empty** location (no stock in the WMS), nearest first (`putaway_sequence`).

No capacity check for now. **Overriding is quick:** the worker simply scans a different location instead of the
suggested one. The reason is optional, one tap from the short list.

Confirming a task = worker scans LPN, then location. One transaction: task → DONE, ledger `MOVE` (−R-RECV, +R3-S5-2,
same LPN, same `txn_group_id`), `lpns.current_location_id` and status updated.

### 3.9 Cycle counts (later, Phase 4+)

**`count_tasks`** (`scope`: location / SKU / LPN, `status`, `blind` boolean, assigned/created/completed who/when) and
**`count_lines`** (`count_task_id`, `location_id`, `lpn_id`, `sku_id`, `counted_qty` CK `>= 0`, `system_qty_at_count`,
`counted_by/at`). Differences become `COUNT` ledger rows with a reason, through the same approval rule as adjustments
(more than the smaller of 50 pieces or one full carton needs a supervisor; same settings).
Only the structure is fixed now; details later.

### 3.10 Cross-cutting

**`idempotency_keys`**: makes every scan safe against double-taps and network retries (see §5.3).
`key uuid` PK, `user_id`, `endpoint`, `request_hash`, `response jsonb`, `created_at`. Old keys may be purged after 30 days
(they are not business history).

**`app_settings`**: business thresholds, changeable without a code change.
`key` PK, `value jsonb`, `description`, `updated_by`, `updated_at`. Every change goes to `audit_log`. Initial rows:
`adjustment_approval_max_pcs = 50`, `adjustment_approval_use_carton = true` (also used for count differences).

**`audit_log`**: who changed what on master data and document headers.
`table_name`, `row_id`, `action` CK `IN ('INSERT','UPDATE','STATUS')`, `old_values jsonb`, `new_values jsonb`,
`user_id`, `at`. Filled by triggers. Append-only like the ledger.

---

## 4. How the receiving flow maps to the tables

| Step | What happens in the database |
|---|---|
| 1. Import packing list | `file_uploads` + `inbound_order_imports` + `inbound_orders` (DRAFT) + `inbound_order_lines` + `inbound_order_line_sizes`. Profile from `supplier_import_profiles` decides rows/columns/dates and how sizes are read (none / column / grid). |
| 2. Validation | `inbound_import_issues`. Sample file gives: `UNKNOWN_STYLE` (`VDP-VDP-2057`, row 13), `UNKNOWN_COLOR` for each new supplier color (e.g. `leo with black`), `MISSING_INVOICE_NO` (cell shows `#REF!`, warning). Totals: 466 cartons / 22,624 units, they match the lines. For each unknown style, color or size the manager either **maps** it to an existing one (optionally saving an alias for next time) or **creates a new one** right there (brand required for a new style). Order → OPEN only with zero open ERRORs; a missing invoice number does not block receiving, only closing. |
| 3. Truck arrives | `receipts` (OPEN) with BOL, carton count, damage notes, photos. More trucks = more receipts on the same order. |
| 4. Scanning | Worker scans an LPN → `receipt_cartons` (LPN status `ISSUED` → `RECEIVED`). Then the contents → `receipt_carton_lines` (several sizes for a prepack). "Same as last" copies the previous carton's lines into the new carton (`copied_from_id`); the new LPN is still scanned. A wrong scan is voided and its LPN burned; the carton gets a new label. |
| 5. Blind | The worker's screens and API never return `expected_qty` (permission on the API; workers get no read access to `inbound_order_lines` quantities). The worker sees only what they scanned and the BOL carton count. |
| 6. Finish | One transaction locks the receipt, compares, and writes `receipt_variances`. All non-voided cartons are posted: ledger `RECEIVE` into `R-RECV` (or `R-DAMAGE` for damaged cartons). Cartons of lines with an open variance get an `inventory_holds` row. Status → FINISHED. |
| 7. Approval | Supervisor accepts/rejects each variance. No open variance → receipt APPROVED, holds released, `putaway_tasks` created. |
| 8. Put-away | WMS suggests a location (same SKU first, else nearest empty). Worker scans LPN, then the suggested or any other location. Ledger `MOVE`. |
| 9. Close order | All lines received and all receipts approved → CLOSED. Otherwise a manager sets CLOSED_SHORT with a reason. Both need the invoice number. |

Why stock is posted at **Finish** and not at each scan: the ledger then only contains cartons that were confirmed at
Finish. Wrong scans before Finish are voided in `receipt_cartons` (still recorded) and never touch stock.

---

## 5. "Strong database": how each requirement is met

### 5.1 Foreign keys, unique and check constraints
- Every reference is a real FK with `RESTRICT` (no cascades; the draft's `CASCADE` on barcodes is removed).
- Composite FKs make sure a size row on an expected line always belongs to that line's style and color.
- Uniques that encode business rules: LPN code (forever), LPN received once (`receipt_cartons.lpn_id`), barcode → one SKU,
  SKU = one style+color+size, invoice per supplier, BOL per order, one open put-away task / hold per LPN,
  non-overlapping LPN batches (`EXCLUDE`), one balance row per SKU+location+LPN.
- Checks: quantities `> 0` on documents, `qty <> 0` in the ledger, `qty_on_hand >= 0`, statuses from fixed lists,
  "who and when" required together with every decision (approve, void, close short, resolve), location code always equal
  to its coordinates, approver ≠ requester, invoice number required to close an order.
- Fallback if `btree_gist` is not available: LPN ranges are protected only by the `lpn_counters` lock plus UQ on
  `lpns.code` (an overlapping batch would fail on the first duplicate code).

### 5.2 Ledger is append-only; stock = sum of transactions
- Triggers refuse `UPDATE`, `DELETE` and `TRUNCATE` on `inventory_transactions` and `audit_log`.
- From Phase 4 the app's database role has no rights to do it either (defence in depth). The triggers apply from the
  first Phase 3 migration.
- `inventory_balances` is written only by the ledger trigger, in the same transaction. A nightly check compares it with
  `Σ ledger` and raises an alert on any difference; the balance table can be rebuilt from the ledger at any time.

### 5.3 Many phones at once; double-taps
- **Double-tap / retry:** each scan action on the phone gets a new UUID (`Idempotency-Key` header). The server inserts it
  into `idempotency_keys` **in the same transaction** as the scan. A second request with the same key hits the PK, and the
  server returns the first answer instead of writing again. Natural uniques (LPN received once) are a second safety net:
  even without the key, the same LPN can't be received twice.
- **Locking:** short transactions in READ COMMITTED with explicit row locks:
  - balance rows: locked by the `ON CONFLICT DO UPDATE` itself; when one action touches several balances, they are
    touched in a fixed order (`sku_id, location_id, lpn_id`) so two phones can't deadlock each other;
  - receipts: scans take `FOR SHARE` on the receipt row; Finish takes `FOR UPDATE`. Finish waits for scans in progress,
    and a scan that arrives after Finish sees status FINISHED and is refused;
  - LPN issuing: `FOR UPDATE` on `lpn_counters`;
  - put-away confirm: `FOR UPDATE` on the task and the LPN row.
- **Screens edited by managers** (order header, lines): `row_version` check. If two people edit at once, the second
  save gets "changed by someone else, reload" instead of silently overwriting.

### 5.4 Who and when on every change
- `created_by` / `created_at` NOT NULL everywhere, `updated_by` / `updated_at` on mutable rows, timestamps from the DB clock.
- The app sets `SET LOCAL app.user_id = <id>` at the start of every request transaction. Audit triggers read it and
  **refuse the write if it is missing**, so no code path can change data anonymously.
- Decisions (approve, reject, void, close short, release hold) have their own who/when columns, enforced by checks.
- Phones also record `device_name` (as QR picking already does).

### 5.5 Indexes for common lookups
| Lookup | Index |
|---|---|
| Scan an LPN | UQ `lpns(code)` |
| Scan a UPC | UQ `sku_barcodes(barcode)` |
| Scan / type a location | UQ `locations(code)` |
| Find a style | UQ `styles(code)` + trigram index on `styles(code)` for "contains" search (`pg_trgm`; fallback without it: prefix search on the UQ index) |
| Put-away suggestion | `inventory_balances(sku_id, location_id) WHERE qty_on_hand > 0` and `locations(putaway_sequence) WHERE is_active AND location_type = 'STORAGE'` |
| Stock of a SKU | `inventory_balances(sku_id) WHERE qty_on_hand > 0` |
| What is in a location | `inventory_balances(location_id) WHERE qty_on_hand > 0` |
| History of a SKU / location / LPN | `inventory_transactions(sku_id, created_at)`, `(location_id, created_at)`, `(lpn_id)` |
| Open orders / receipts | `inbound_orders(status) WHERE status NOT IN ('CLOSED','CLOSED_SHORT','CANCELLED')`, same idea for receipts |
| Cartons of a receipt | `receipt_cartons(receipt_id)` |
| Open put-away work | `putaway_tasks(status, assigned_to) WHERE status = 'OPEN'` |
| Every FK column | its own index |

### 5.6 Existing data and the Part 2 relocation
- **Part 1 (Allbirds): nothing changes**, including its receiving (current inbound screens stay). Its rows, locations
  and history stay in `inventory_items` / `stock_movements`. No migration or script touches them. Moving Part 1 to the
  new model is a separate decision for later (CLAUDE.md rule 7).
- **Catalog backfill (read-only on old data):** `brands`, `styles`, `colors`, `sizes`, `skus` for VD/VO/ED are created by
  reading distinct values from `inventory_items` (Part 2 only). Old rows are not modified. Near-duplicates are listed for
  you, not merged automatically.
- **Part 2 relocation = opening balance:**
  1. `locations` are created for the new `R<row>-S<section>-<level>` list (+ R-RECV, R-STAGE, R-DAMAGE).
  2. The fresh count is entered as `OPENING` ledger rows (with who/when, and `legacy_item_id` where it matches an old row).
  3. Each old Part 2 row is brought to 0 and deactivated **in the app** (recorded movement, history kept), as decided for
     the duplicates. No direct SQL.
  4. Check before switching: count totals per SKU reviewed by you; differences vs. the old rows are shown, not hidden.
- **During the transition** the dashboard and lookups read Part 1 from the old tables and Part 2 from the new ones
  (one read-only view that combines both).
- **Draft branch `draft/wms-models-v2`:** kept as input. Taken over: brand → style → SKU → barcode, zone → location,
  LPN, balance + ledger idea, partial unique for loose vs. LPN stock. Changed: `timestamptz`, `created_by` FKs, append-only
  enforced in the DB, balances written only by the ledger, no cascades, location format `R3-S5-2` instead of
  `P2-R05-S12-3`, explicit document FKs instead of `ref_type/ref_id` text, `user_name` text → user FK.
- **Possible stray tables:** if production already has tables named `brands`, `skus`, `lpns`, `inventory_balances`,
  … (HANDOFF item 5), the first Phase 3 migration checks them. Empty stray tables are dropped (decided). If any of them
  holds rows, the migration stops, changes nothing, and lists them so you can look first.

---

## 6. Decisions (review of 2026-11-21) and what is still open

| # | Topic | Decision |
|---|---|---|
| 1 | Postgres version, extensions | Checked during the 1b schema check (pg_dump 18 worked against production on 2026-11-21). Fallbacks kept for `btree_gist` and `pg_trgm`. |
| 2 | Separate app DB role | Yes, in **Phase 4** (second `DATABASE_URL` then). Ledger triggers protect from day one. |
| 3 | Stray v2 tables | Dropped only if empty. Otherwise the migration stops and shows them. |
| 4 | Voided LPN | Burned. The worker uses a new label. |
| 5 | Sample file layout | Header rows 10–11, data from row 12 (`CI2025VD003`). No other version. |
| 6 | Pack size × cartons ≠ quantity | Warning only. |
| 7 | Adjustment approval | Supervisor needed above the smaller of 50 pieces or one full carton. Stored in `app_settings`. Same rule for count differences. |
| 8 | Missing invoice number | Receiving allowed; required before closing (DB check). |
| 9 | Put-away suggestions | No fixed rows per brand, no capacity check. Same SKU first, else nearest empty location. Override = scan another location; reason optional from a short list. `max_cartons` kept optional. |
| 10 | Stock per LPN after put-away | Yes, kept per LPN. |
| 11 | Floor and wall names | Proposed: floor = level 0 (`R3-S5-0`), wall = `W-S<section>-<level>` (§3.6). Final names when the Part 2 layout is collected. |
| 12 | Sizes | Profile supports no size column (default OS), a size column, and a size grid. Prepacks: per-carton size breakdown in `inbound_order_line_sizes`. |
| 13 | Allbirds receiving | Stays exactly as it is. New receiving is Part 2 only. |
| 14 | Over-receipt | Always a variance for a supervisor. |
| — | New styles/colors/sizes at import | A manager can create them from the import screen, with who/when and the import recorded (§3.1, §3.3). |
| — | Put-away override reasons | Confirmed: `LOCATION_FULL`, `CLOSER_SPOT`, `SAME_STYLE_NEARBY`, `OTHER`. |
| — | Prepacks as master data | Not now. The per-line size breakdown from the packing list (`inbound_order_line_sizes`) is enough. |

**Still open (does not block writing the Phase 3 migrations):**
1. **Part 2 layout:** the list of rows, sections and levels, the wall sections, and whether any section has two separate
   floor spots (front and back). Also the walking order from the dock (`putaway_sequence`, used for "nearest first").
   Stays open until the relocation step.

---

## 7. What happens next (after approval)

Phase 3 migrations are written in small reversible steps (expand only: new tables, no change to old ones), with tests
for every constraint and trigger listed above (including two parallel sessions for the locking cases), on the local dev
database. Nothing touches production until you approve a deploy.
