"""Part 2 (VD & VO, Rows) only: one ACTIVE row per location + style + color + size + pack size.

Partial unique index on inventory_items WHERE is_active AND warehouse_part = 'PART_2'
(exact definition: app/inventory_slots.py). Part 1 (Allbirds, Lines) is NOT covered and keeps
one row per carton. Deactivated rows are not affected.

This migration changes NO data, in any part of the warehouse. If Part 2 already has duplicate
active rows it REFUSES to run and changes nothing: it prints a summary. Full list (read-only):
    python scripts/report_duplicate_active_rows.py

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.inventory_slots import (
    ACTIVE_SLOT_EXPRESSIONS, ACTIVE_SLOT_INDEX, ACTIVE_SLOT_WHERE, duplicate_summary, find_duplicate_active_slots,
)


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    groups, rows = duplicate_summary(bind)
    if groups:
        examples = "\n".join(
            f"  {d['style']} / {d['color']} / size {d['size']} / {d['pcs_per_box']} pcs/box @ {d['location']}: "
            f"{d['rows']} active rows (ids {d['ids'][:10]}{' ...' if len(d['ids']) > 10 else ''})"
            for d in find_duplicate_active_slots(bind, limit=10)
        )
        raise RuntimeError(
            f"Migration 0003 NOT applied, nothing changed: {groups} Part 2 slot(s) "
            f"have more than one active row ({rows} rows involved). Largest groups:\n{examples}\n"
            "Full list: python scripts/report_duplicate_active_rows.py"
        )
    op.create_index(
        ACTIVE_SLOT_INDEX,
        "inventory_items",
        [sa.text(expr) for expr in ACTIVE_SLOT_EXPRESSIONS],
        unique=True,
        postgresql_where=sa.text(ACTIVE_SLOT_WHERE),
    )


def downgrade() -> None:
    op.drop_index(ACTIVE_SLOT_INDEX, table_name="inventory_items")
