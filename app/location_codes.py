"""
Part 2 location codes (table `locations`, migration 0004). Part 1 (Allbirds, Lines) is NOT covered.

Codes (decided 2026-11-21; wall changed 2026-11-26: the wall has no section numbers):
  shelf         R<row>-S<section>-L<level>   e.g. R3-S5-L2
  ground front  R<row>-GF-L<level>           e.g. R3-GF-L1
  ground back   R<row>-GB-L<level>           e.g. R3-GB-L2
  wall front    W-SF-L<level>                e.g. W-SF-L1
  wall back     W-SB-L<level>                e.g. W-SB-L2
  special       R-RECV, R-STAGE, R-DAMAGE    (no coordinates)
Every storage spot has a level (>= 1). The check constraints below make the database refuse any code that
disagrees with its coordinates; model and migration share them so they cannot drift apart.
"""

LOCATION_TYPES = ("STORAGE", "RECEIVING", "STAGING", "DAMAGE")
AREAS = ("SHELF", "GROUND_FRONT", "GROUND_BACK", "WALL_FRONT", "WALL_BACK")

LOCATION_CHECKS = {
    "ck_locations_code_upper": "code = upper(btrim(code))",
    "ck_locations_type": "location_type IN ('STORAGE', 'RECEIVING', 'STAGING', 'DAMAGE')",
    "ck_locations_area": "area IN ('SHELF', 'GROUND_FRONT', 'GROUND_BACK', 'WALL_FRONT', 'WALL_BACK')",
    "ck_locations_level_positive": "level_no >= 1",
    "ck_locations_row_positive": "row_no >= 1",
    "ck_locations_section_positive": "section_no >= 1",
    "ck_locations_max_cartons_positive": "max_cartons >= 1",
    "ck_locations_code_matches": (
        "CASE "
        "WHEN location_type <> 'STORAGE' THEN area IS NULL AND row_no IS NULL AND section_no IS NULL "
        "AND level_no IS NULL AND code ~ '^R-[A-Z]+$' "
        "WHEN area = 'SHELF' THEN row_no IS NOT NULL AND section_no IS NOT NULL AND level_no IS NOT NULL "
        "AND code = 'R' || row_no || '-S' || section_no || '-L' || level_no "
        "WHEN area = 'GROUND_FRONT' THEN row_no IS NOT NULL AND section_no IS NULL AND level_no IS NOT NULL "
        "AND code = 'R' || row_no || '-GF-L' || level_no "
        "WHEN area = 'GROUND_BACK' THEN row_no IS NOT NULL AND section_no IS NULL AND level_no IS NOT NULL "
        "AND code = 'R' || row_no || '-GB-L' || level_no "
        "WHEN area = 'WALL_FRONT' THEN row_no IS NULL AND section_no IS NULL AND level_no IS NOT NULL "
        "AND code = 'W-SF-L' || level_no "
        "WHEN area = 'WALL_BACK' THEN row_no IS NULL AND section_no IS NULL AND level_no IS NOT NULL "
        "AND code = 'W-SB-L' || level_no "
        "ELSE false END"
    ),
}

# location_changes: one row per create / deactivate / reactivate. Append-only: the trigger refuses UPDATE,
# DELETE and TRUNCATE, so the record of who changed which spot can never be rewritten.
LOCATION_CHANGE_ACTIONS_CHECK = "action IN ('CREATE', 'DEACTIVATE', 'REACTIVATE')"
APPEND_ONLY_FUNCTION = (
    "CREATE FUNCTION location_changes_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN RAISE EXCEPTION 'location_changes is append-only (% refused)', TG_OP; END $$"
)

# inventory_items.location_id may only be set on Part 2 rows: Allbirds can never be linked.
ITEM_LOCATION_CHECK_NAME = "ck_inventory_items_location_part2_only"
ITEM_LOCATION_CHECK = "location_id IS NULL OR warehouse_part = 'PART_2'"


def storage_code(area: str, level: int, row: int | None = None, section: int | None = None) -> str:
    """The code for a storage spot, exactly as the database check expects it."""
    if area == "SHELF":
        return f"R{row}-S{section}-L{level}"
    if area == "GROUND_FRONT":
        return f"R{row}-GF-L{level}"
    if area == "GROUND_BACK":
        return f"R{row}-GB-L{level}"
    if area == "WALL_FRONT":
        return f"W-SF-L{level}"
    if area == "WALL_BACK":
        return f"W-SB-L{level}"
    raise ValueError(f"unknown area {area!r}")
