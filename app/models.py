from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from .database import Base


class WarehouseLocation(Base):
    """
    Master physical location map for the 50,000+ sq ft warehouse:
      - PART_1: Allbirds Zone -> 14 Lines (Line 1..14), each 32-35+ Sections, 4 Levels
      - PART_2: Von Dutch & Valentino Zone -> 14 Rows (Row 1..14 + WALL), each 36 Sections
                plus Ground FRONT, Ground BACK, and WALL placements, 4 Levels
    """
    __tablename__ = "warehouse_locations"

    id = Column(Integer, primary_key=True, index=True)
    location_code = Column(String(120), unique=True, index=True, nullable=False)
    warehouse_part = Column(String(30), index=True, nullable=False)   # PART_1 | PART_2
    zone_label = Column(String(100), nullable=False)                  # Allbirds Zone | Von Dutch & Valentino Zone
    aisle_type = Column(String(20), index=True, nullable=False)       # LINE | ROW | WALL
    aisle_number = Column(String(30), index=True, nullable=False)     # 1..14 or WALL
    section = Column(String(50), index=True, nullable=False)          # 1..36, FRONT, BACK, WALL
    level = Column(String(30), index=True, nullable=False)            # 1..4
    placement_type = Column(String(30), index=True, nullable=False)   # RACK | GROUND_FRONT | GROUND_BACK | WALL
    display_location = Column(String(200), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    style = Column(String(100), index=True, nullable=False)           # e.g. "A12501", "VDSW-2092 SND", "VOSB-028"
    brand = Column(String(60), index=True, default="ALLBIRDS")        # ALLBIRDS | VON DUTCH | VALENTINO | ED HARDY
    warehouse_part = Column(String(30), index=True, default="PART_1") # PART_1 (Lines) | PART_2 (Rows/Ground/Wall)
    placement_type = Column(String(30), index=True, default="RACK")   # RACK | GROUND_FRONT | GROUND_BACK | WALL
    color = Column(String(100), index=True, default="STANDARD")
    size = Column(String(50), index=True, default="OS")
    line = Column(String(50), index=True, nullable=True)              # Part 1: Line 1..14
    section = Column(String(50), index=True, nullable=True)           # Sec 1..36 or FRONT / BACK / WALL
    level = Column(String(50), index=True, nullable=True)             # Lvl 1..4
    row_pos = Column(String(50), index=True, nullable=True)           # Part 2: Row 1..14 or WALL
    box_num = Column(String(50), nullable=True)                       # Box # / Cartons
    location_code = Column(String(120), index=True, nullable=True)    # Links to WarehouseLocation.location_code
    location = Column(String(200), index=True, nullable=False, default="Unassigned")
    pcs_per_box = Column(Integer, nullable=True)
    quantity = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_item_style_loc", "style", "location"),
        Index("idx_item_style_size_color", "style", "size", "color"),
        Index("idx_item_part_line_sec", "warehouse_part", "line", "row_pos", "section", "level"),
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
    change_amount = Column(Integer, nullable=False)
    quantity_after = Column(Integer, nullable=False)
    movement_type = Column(String(50), default="QUICK_ADJUST")
    reason = Column(String(255), nullable=True)
    staff_name = Column(String(100), default="Manager")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    item = relationship("InventoryItem", back_populates="movements")


class WarehouseUser(Base):
    """
    User accounts & access control for Warehouse OS:
      - role: ADMIN | MANAGER | PART_1_LEAD | PART_2_LEAD | STAFF
      - assigned_zone: ALL_ZONES | PART_1_ALLBIRDS | PART_2_VD_VALENTINO
      - is_approved: 1 (Approved/Active), 0 (Pending Admin Approval), -1 (Revoked/Blocked)
    """
    __tablename__ = "warehouse_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=True)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="STAFF", nullable=False)
    assigned_zone = Column(String(80), default="ALL_ZONES", nullable=False)
    is_approved = Column(Integer, default=0, nullable=False, index=True)  # 1=Active, 0=Pending, -1=Revoked
    session_token = Column(String(128), index=True, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class InboundShipment(Base):
    """
    Tracks inbound warehouse shipments (1 to 20 pallets, 8 to 40 boxes/pallet).
    Stores uploaded Packing List & Commercial Invoice document scans/photos,
    AI extracted line items, verified shelf locations, and Admin approval state.
    """
    __tablename__ = "inbound_shipments"

    id = Column(Integer, primary_key=True, index=True)
    shipment_number = Column(String(100), unique=True, index=True, nullable=False)
    po_number = Column(String(100), index=True, nullable=True)
    carrier_vendor = Column(String(150), nullable=True)
    pallets_count = Column(Integer, default=1, nullable=False)
    total_boxes = Column(Integer, default=0, nullable=False)
    total_units = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="PENDING_APPROVAL", index=True, nullable=False)  # PENDING_APPROVAL | APPROVED | REJECTED | DRAFT
    packing_list_filename = Column(String(255), nullable=True)
    packing_list_data = Column(Text, nullable=True)          # Base64 data URI for instant in-browser preview
    commercial_invoice_filename = Column(String(255), nullable=True)
    commercial_invoice_data = Column(Text, nullable=True)   # Base64 data URI
    ai_extracted_raw = Column(Text, nullable=True)          # Raw JSON from LLM document parser
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), default="Warehouse Manager", nullable=False)
    approved_by = Column(String(120), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship(
        "InboundShipmentItem",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="InboundShipmentItem.id"
    )


class InboundShipmentItem(Base):
    """
    Staged item line in an inbound shipment.
    Records style, color, size, quantity, box count, and physical warehouse shelf location
    entered by the Manager before committing to live inventory.
    """
    __tablename__ = "inbound_shipment_items"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("inbound_shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    style = Column(String(100), index=True, nullable=False)
    brand = Column(String(60), default="ALLBIRDS")
    warehouse_part = Column(String(30), default="PART_1")
    color = Column(String(100), default="STANDARD")
    size = Column(String(50), default="OS")
    line = Column(String(50), nullable=True)
    row_pos = Column(String(50), nullable=True)
    section = Column(String(50), nullable=True)
    level = Column(String(50), nullable=True)
    box_num = Column(String(50), nullable=True)
    box_count = Column(Integer, default=1)
    pcs_per_box = Column(Integer, nullable=True)
    quantity = Column(Integer, default=0, nullable=False)       # Received physical units
    expected_quantity = Column(Integer, nullable=True)          # Quantity per packing list/invoice
    location = Column(String(200), default="Unassigned")
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("InboundShipment", back_populates="items")
