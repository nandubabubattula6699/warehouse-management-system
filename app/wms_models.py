"""
Industrial WMS core data model (v2).

    Brand -> Product (style) -> SKU (style + color + size) -> SkuBarcode (UPC / EAN / alias)
    Zone  -> Bin (scannable location label, e.g. P2-R05-S12-3)
    InventoryBalance  = SKU x Bin (x LPN) -> qty on hand   (current state, fast lookup)
    InventoryTxn      = append-only ledger of every stock change (receive, putaway, pick, move, adjust, count)

These tables live alongside the legacy `inventory_items` table during migration.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    String, UniqueConstraint, text,
)
from sqlalchemy.orm import relationship

from .database import Base


# ---------------------------------------------------------------- MASTER DATA
class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False, index=True)    # VD | VO | AB | ED
    name = Column(String(80), unique=True, nullable=False)                # VON DUTCH | VALENTINO | ALLBIRDS | ED HARDY
    default_zone_code = Column(String(20), nullable=True)                 # P1 | P2
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    products = relationship("Product", back_populates="brand")


class Product(Base):
    """One row per style."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    style_code = Column(String(100), nullable=False, index=True)          # VDSW-2092, A12501
    description = Column(String(255), nullable=True)
    category = Column(String(80), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("brand_id", "style_code", name="uq_product_brand_style"),)

    brand = relationship("Brand", back_populates="products")
    skus = relationship("Sku", back_populates="product")


class Sku(Base):
    """One row per sellable variant: style + color + size."""
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    sku_code = Column(String(160), unique=True, nullable=False, index=True)   # VDSW-2092|SAND|M
    color_code = Column(String(40), nullable=True)
    color_name = Column(String(100), nullable=False, default="STANDARD")
    size = Column(String(40), nullable=False, default="OS")
    pcs_per_carton = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")             # ACTIVE | DISCONTINUED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "color_name", "size", name="uq_sku_variant"),
    )

    product = relationship("Product", back_populates="skus")
    barcodes = relationship("SkuBarcode", back_populates="sku", cascade="all, delete-orphan")
    balances = relationship("InventoryBalance", back_populates="sku")


class SkuBarcode(Base):
    """Every scannable code that resolves to a SKU. A barcode maps to exactly one SKU."""
    __tablename__ = "sku_barcodes"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    barcode = Column(String(64), unique=True, nullable=False, index=True)
    barcode_type = Column(String(20), nullable=False, default="UPC_A")       # UPC_A | EAN13 | GTIN14 | VENDOR | INTERNAL
    is_primary = Column(Boolean, default=False, nullable=False)
    source = Column(String(80), nullable=True)                                # e.g. vendor UPC file name
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sku = relationship("Sku", back_populates="barcodes")


# ----------------------------------------------------------------- LOCATIONS
class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)      # P1 | P2 | P2-WL | DOCK | STG
    name = Column(String(100), nullable=False)
    zone_type = Column(String(20), nullable=False, default="STORAGE")       # STORAGE | RECEIVING | STAGING | SHIPPING

    bins = relationship("Bin", back_populates="zone")


class Bin(Base):
    """A single physical, labelled storage position. `bin_code` is printed as a Code 128 barcode."""
    __tablename__ = "bins"

    id = Column(Integer, primary_key=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False, index=True)
    bin_code = Column(String(40), unique=True, nullable=False, index=True)  # P2-R05-S12-3
    aisle_type = Column(String(10), nullable=False)                          # LINE | ROW | WALL | DOCK | STG
    aisle = Column(String(10), nullable=True)                                # 05 | WL
    section = Column(String(10), nullable=True)                              # 12 | GF | GB
    level = Column(String(10), nullable=True)                                # 1..4
    bin_type = Column(String(20), nullable=False, default="RACK")            # RACK | FLOOR | WALL | DOCK | STAGING
    display_name = Column(String(120), nullable=False)                       # Row 5 • Sec 12 • Lvl 3
    pick_sequence = Column(Integer, nullable=True, index=True)               # walking order
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    zone = relationship("Zone", back_populates="bins")
    balances = relationship("InventoryBalance", back_populates="bin")


class Lpn(Base):
    """License plate: a labelled carton or pallet (phase 2)."""
    __tablename__ = "lpns"

    id = Column(Integer, primary_key=True)
    lpn_code = Column(String(40), unique=True, nullable=False, index=True)
    lpn_type = Column(String(10), nullable=False, default="CARTON")          # CARTON | PALLET
    bin_id = Column(Integer, ForeignKey("bins.id"), nullable=True, index=True)
    parent_lpn_id = Column(Integer, ForeignKey("lpns.id"), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ----------------------------------------------------------------- INVENTORY
class InventoryBalance(Base):
    """Current stock of one SKU in one bin. Maintained only via InventoryTxn posting."""
    __tablename__ = "inventory_balances"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    bin_id = Column(Integer, ForeignKey("bins.id"), nullable=False, index=True)
    lpn_id = Column(Integer, ForeignKey("lpns.id"), nullable=True, index=True)
    qty_on_hand = Column(Integer, nullable=False, default=0)
    qty_allocated = Column(Integer, nullable=False, default=0)
    carton_count = Column(Integer, nullable=True)                            # informational (legacy "Box #")
    last_counted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        # NULLs are distinct in unique constraints, so loose (non-LPN) stock gets its own partial unique index
        Index("uq_balance_sku_bin_loose", "sku_id", "bin_id", unique=True,
              postgresql_where=text("lpn_id IS NULL"), sqlite_where=text("lpn_id IS NULL")),
        Index("uq_balance_sku_bin_lpn", "sku_id", "bin_id", "lpn_id", unique=True,
              postgresql_where=text("lpn_id IS NOT NULL"), sqlite_where=text("lpn_id IS NOT NULL")),
        CheckConstraint("qty_on_hand >= 0", name="ck_balance_non_negative"),
        CheckConstraint("qty_allocated >= 0", name="ck_balance_alloc_non_negative"),
        Index("idx_balance_bin_sku", "bin_id", "sku_id"),
    )

    sku = relationship("Sku", back_populates="balances")
    bin = relationship("Bin", back_populates="balances")


class InventoryTxn(Base):
    """Append-only stock ledger. Never updated or deleted; corrections are new rows."""
    __tablename__ = "inventory_txns"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    bin_id = Column(Integer, ForeignKey("bins.id"), nullable=False, index=True)
    lpn_id = Column(Integer, ForeignKey("lpns.id"), nullable=True)
    txn_type = Column(String(20), nullable=False, index=True)   # OPENING | RECEIVE | PUTAWAY | PICK | MOVE | ADJUST | COUNT
    qty_delta = Column(Integer, nullable=False)
    qty_after = Column(Integer, nullable=False)
    move_group = Column(String(40), nullable=True, index=True)  # links the -/+ legs of a MOVE
    ref_type = Column(String(30), nullable=True)                # INBOUND_SHIPMENT | ORDER | COUNT_TASK | LEGACY_ITEM
    ref_id = Column(String(60), nullable=True)
    scanned_barcode = Column(String(64), nullable=True)
    reason = Column(String(255), nullable=True)
    user_name = Column(String(120), nullable=False, default="SYSTEM")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_txn_sku_created", "sku_id", "created_at"),
        Index("idx_txn_ref", "ref_type", "ref_id"),
    )
