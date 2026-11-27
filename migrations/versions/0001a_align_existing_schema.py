"""Align an existing (stamped) database with the 0001 baseline. Changes no rows.

Staging (and very likely production) was built by the old startup code, which added brand,
warehouse_part, placement_type and location_code later with ALTER TABLE. Its schema dump
(2026-11-26) differs from the baseline in exactly two ways that matter:

1. Five inventory_items indexes are missing. They are created here with IF NOT EXISTS, so on a
   fresh database built by 0001 (where they already exist) this does nothing.
2. brand / warehouse_part / placement_type carry server defaults ('ALLBIRDS', 'PART_1', 'RACK').
   Every insert path sets all three explicitly (build_location_info), so the defaults never fire;
   they are dropped so a Part 2 row can never silently become an Allbirds/Part 1/Rack row.
   DROP DEFAULT on a column without a default is a no-op.

Column order (the later columns sit at the end) is not changed: it does not affect the app and
compare_schema.py ignores it.

Revision ID: 0001a
Revises: 0001
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0001a'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    ("idx_item_part_line_sec", "warehouse_part, line, row_pos, section, level"),
    ("ix_inventory_items_brand", "brand"),
    ("ix_inventory_items_location_code", "location_code"),
    ("ix_inventory_items_placement_type", "placement_type"),
    ("ix_inventory_items_warehouse_part", "warehouse_part"),
)
_DEFAULT_COLUMNS = ("brand", "warehouse_part", "placement_type")


def upgrade() -> None:
    for name, cols in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON inventory_items USING btree ({cols})")
    for col in _DEFAULT_COLUMNS:
        op.execute(f"ALTER TABLE inventory_items ALTER COLUMN {col} DROP DEFAULT")


def downgrade() -> None:
    # Intentionally no schema change. After this upgrade every database is exactly the 0001 baseline,
    # and revision 0001 means "the baseline". Dropping the indexes would break 0001's own downgrade
    # on a fresh database, and restoring the old drift (missing indexes, ALLBIRDS/PART_1/RACK
    # defaults) would make a 0001-stamped database differ from the baseline again.
    pass
