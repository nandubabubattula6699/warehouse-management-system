from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from .database import Base

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    style = Column(String(100), index=True, nullable=False)   # Style / SKU code e.g. "A12501"
    color = Column(String(100), index=True, default="STANDARD")
    size = Column(String(50), index=True, default="OS")
    line = Column(String(50), index=True, nullable=True)
    section = Column(String(50), index=True, nullable=True)
    level = Column(String(50), index=True, nullable=True)
    row_pos = Column(String(50), index=True, nullable=True)
    box_num = Column(String(50), nullable=True)
    location = Column(String(200), index=True, nullable=False, default="Unassigned")
    pcs_per_box = Column(Integer, nullable=True)
    quantity = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_item_style_loc", "style", "location"),
        Index("idx_item_style_size_color", "style", "size", "color"),
    )

    movements = relationship(
        "StockMovement",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="desc(StockMovement.created_at)"
    )

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    style = Column(String(100), index=True, nullable=False)
    change_amount = Column(Integer, nullable=False)  # e.g., +5, -1
    quantity_after = Column(Integer, nullable=False)
    movement_type = Column(String(50), default="QUICK_ADJUST")  # QUICK_ADD, QUICK_SUB, STOCK_IN, STOCK_OUT, SET_EXACT
    reason = Column(String(255), nullable=True)
    staff_name = Column(String(100), default="Manager")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    item = relationship("InventoryItem", back_populates="movements")
