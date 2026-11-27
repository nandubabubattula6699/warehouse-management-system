from datetime import datetime
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Integer, String, DateTime, ForeignKey, Identity,
                        Index, Text, UniqueConstraint, func, text, true)
from sqlalchemy.orm import relationship
from .database import Base
from .inventory_slots import ACTIVE_SLOT_EXPRESSIONS, ACTIVE_SLOT_INDEX, ACTIVE_SLOT_WHERE
from .location_codes import ITEM_LOCATION_CHECK, ITEM_LOCATION_CHECK_NAME, LOCATION_CHANGE_ACTIONS_CHECK, LOCATION_CHECKS


class Location(Base):
    """
    Part 2 location master (migration 0004): one row per physical spot, e.g. R3-S5-L2, R3-GF-L1, W-SB-L2, R-RECV.
    Codes and their checks: app/location_codes.py. Never deleted: deactivated (is_active = false).
    Part 1 (Allbirds, Lines) keeps using warehouse_locations and is not linked here.
    """
    __tablename__ = "locations"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    code = Column(String(30), nullable=False)
    location_type = Column(String(20), nullable=False)    # STORAGE | RECEIVING | STAGING | DAMAGE
    area = Column(String(20), nullable=True)              # STORAGE only: SHELF | GROUND_FRONT | GROUND_BACK | WALL_FRONT | WALL_BACK
    row_no = Column(Integer, nullable=True)
    section_no = Column(Integer, nullable=True)
    level_no = Column(Integer, nullable=True)
    putaway_sequence = Column(Integer, nullable=True)     # walking order from the dock (later)
    max_cartons = Column(Integer, nullable=True)          # optional capacity, not used yet
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey("warehouse_users.id", ondelete="RESTRICT"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(Integer, ForeignKey("warehouse_users.id", ondelete="RESTRICT"), nullable=True)
    row_version = Column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        UniqueConstraint("code", name="uq_locations_code"),
        Index("ix_locations_created_by", "created_by"),
        Index("ix_locations_updated_by", "updated_by"),
        Index("ix_locations_row_area", "row_no", "area", "section_no", "level_no"),
        *[CheckConstraint(sql, name=name) for name, sql in LOCATION_CHECKS.items()],
    )


class LocationChange(Base):
    """Append-only (DB trigger): who created / deactivated / reactivated a location, when, and from which file."""
    __tablename__ = "location_changes"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    location_id = Column(BigInteger, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    action = Column(String(20), nullable=False)           # CREATE | DEACTIVATE | REACTIVATE
    source = Column(String(255), nullable=False)          # e.g. "row-size import part2_row_sizes.xlsx sha256:ab12…"
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    changed_by = Column(Integer, ForeignKey("warehouse_users.id", ondelete="RESTRICT"), nullable=False, index=True)

    __table_args__ = (CheckConstraint(LOCATION_CHANGE_ACTIONS_CHECK, name="ck_location_changes_action"),)


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
    # False = deactivated: hidden from lookups/maps/picking, kept for its stock history (never deleted).
    is_active = Column(Boolean, nullable=False, default=True, server_default=true(), index=True)
    # Part 2 only (DB check): link to the locations master. Empty until a recorded linking step fills it.
    location_id = Column(BigInteger, ForeignKey("locations.id", ondelete="RESTRICT",
                                                 name="fk_inventory_items_location_id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(ITEM_LOCATION_CHECK, name=ITEM_LOCATION_CHECK_NAME),
        Index("idx_item_style_loc", "style", "location"),
        Index("idx_item_style_size_color", "style", "size", "color"),
        Index("idx_item_part_line_sec", "warehouse_part", "line", "row_pos", "section", "level"),
        # Part 2 only: one ACTIVE row per location + style + color + size + pack size. Migration 0003;
        # definition shared with app/inventory_slots.py. Part 1 (Lines) keeps one row per carton.
        Index(
            ACTIVE_SLOT_INDEX,
            *[text(expr) for expr in ACTIVE_SLOT_EXPRESSIONS],
            unique=True,
            postgresql_where=text(ACTIVE_SLOT_WHERE),
        ),
    )

    # History is never deleted with its item: the DB foreign key is ON DELETE RESTRICT and
    # passive_deletes="all" stops the ORM from touching movements when an item is deleted.
    movements = relationship(
        "StockMovement",
        back_populates="item",
        cascade="save-update, merge",
        passive_deletes="all",
        order_by="desc(StockMovement.created_at)"
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False, index=True)
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
