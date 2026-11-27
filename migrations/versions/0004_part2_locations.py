"""Part 2 location master (`locations`) and an empty link column `inventory_items.location_id`.

`locations`: one row per physical Part 2 spot. Codes (decided 2026-11-21, wall changed 2026-11-26):
    shelf         R<row>-S<section>-L<level>   e.g. R3-S5-L2
    ground front  R<row>-GF-L<level>           e.g. R3-GF-L1
    ground back   R<row>-GB-L<level>           e.g. R3-GB-L2
    wall front    W-SF-L<level>                e.g. W-SF-L1   (the wall has no section numbers)
    wall back     W-SB-L<level>                e.g. W-SB-L2
    special       R-RECV, R-STAGE, R-DAMAGE    (no coordinates)
Every storage spot has a level (>= 1). Check constraints make the code always agree with its coordinates.
Spots are never deleted: they are deactivated (is_active = false). Every row records who created it.

`inventory_items.location_id`: nullable FK, ON DELETE RESTRICT. Added EMPTY for every row (no row changes).
A check constraint refuses a value on any row that is not Part 2, so Allbirds (Part 1, Lines) can never be
linked. Part 2 rows are linked later in a separate, recorded step.

Creates no locations (they come from the owner's confirmed row-size table) and changes no data.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.location_codes import ITEM_LOCATION_CHECK, ITEM_LOCATION_CHECK_NAME, LOCATION_CHECKS


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=False),
        sa.Column("area", sa.String(length=20), nullable=True),
        sa.Column("row_no", sa.Integer(), nullable=True),
        sa.Column("section_no", sa.Integer(), nullable=True),
        sa.Column("level_no", sa.Integer(), nullable=True),
        sa.Column("putaway_sequence", sa.Integer(), nullable=True),
        sa.Column("max_cartons", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("warehouse_users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("warehouse_users.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint("code", name="uq_locations_code"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in LOCATION_CHECKS.items()],
    )
    op.create_index("ix_locations_created_by", "locations", ["created_by"])
    op.create_index("ix_locations_updated_by", "locations", ["updated_by"])
    op.create_index("ix_locations_row_area", "locations", ["row_no", "area", "section_no", "level_no"])

    # Nullable, no default: existing rows are not rewritten or changed; every row starts unlinked.
    op.add_column("inventory_items", sa.Column("location_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_inventory_items_location_id", "inventory_items", "locations",
                          ["location_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_inventory_items_location_id", "inventory_items", ["location_id"])
    op.create_check_constraint(ITEM_LOCATION_CHECK_NAME, "inventory_items", ITEM_LOCATION_CHECK)


def downgrade() -> None:
    # Refuse instead of silently dropping links that were made in the app.
    linked = op.get_bind().execute(sa.text("SELECT count(*) FROM inventory_items WHERE location_id IS NOT NULL")).scalar()
    if linked:
        raise RuntimeError(f"Downgrade 0004 refused: {linked} inventory rows are linked to a location. Nothing changed.")
    op.drop_constraint(ITEM_LOCATION_CHECK_NAME, "inventory_items", type_="check")
    op.drop_index("ix_inventory_items_location_id", table_name="inventory_items")
    op.drop_constraint("fk_inventory_items_location_id", "inventory_items", type_="foreignkey")
    op.drop_column("inventory_items", "location_id")
    op.drop_index("ix_locations_row_area", table_name="locations")
    op.drop_index("ix_locations_updated_by", table_name="locations")
    op.drop_index("ix_locations_created_by", table_name="locations")
    op.drop_table("locations")
