"""Protect stock history + soft-delete flag for inventory rows.

1. stock_movements.item_id: ON DELETE CASCADE -> ON DELETE RESTRICT.
   The database itself now refuses to delete an inventory row that has movement history
   (before, deleting the row silently erased its whole audit trail).
2. inventory_items.is_active BOOLEAN NOT NULL DEFAULT true (+ index).
   Rows that must disappear from the floor views but keep their history are deactivated
   instead of deleted. Every existing row becomes active (no behaviour change on upgrade).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "stock_movements_item_id_fkey"


def _drop_item_fk() -> None:
    """Drop the stock_movements -> inventory_items FK whatever it is called in this database."""
    for fk in sa.inspect(op.get_bind()).get_foreign_keys("stock_movements"):
        if fk["referred_table"] == "inventory_items" and fk["constrained_columns"] == ["item_id"]:
            op.drop_constraint(fk["name"], "stock_movements", type_="foreignkey")
            return
    raise RuntimeError("stock_movements.item_id foreign key not found - schema differs from the baseline.")


def upgrade() -> None:
    _drop_item_fk()
    op.create_foreign_key(FK_NAME, "stock_movements", "inventory_items", ["item_id"], ["id"],
                          ondelete="RESTRICT")

    op.add_column("inventory_items",
                  sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_index(op.f("ix_inventory_items_is_active"), "inventory_items", ["is_active"], unique=False)


def downgrade() -> None:
    # Deactivated rows become visible again (the flag is dropped); no rows are deleted.
    op.drop_index(op.f("ix_inventory_items_is_active"), table_name="inventory_items")
    op.drop_column("inventory_items", "is_active")

    _drop_item_fk()
    op.create_foreign_key(FK_NAME, "stock_movements", "inventory_items", ["item_id"], ["id"],
                          ondelete="CASCADE")
