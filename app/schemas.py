from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

class ItemBase(BaseModel):
    style: str
    color: str = "STANDARD"
    size: str = "OS"
    line: Optional[str] = None
    section: Optional[str] = None
    level: Optional[str] = None
    row_pos: Optional[str] = None
    box_num: Optional[str] = None
    location: str
    pcs_per_box: Optional[int] = None
    quantity: int = 0

class ItemCreate(ItemBase):
    pass

class ItemUpdatePayload(BaseModel):
    style: str
    color: str = "STANDARD"
    size: str = "OS"
    line: Optional[str] = None
    section: Optional[str] = None
    level: Optional[str] = None
    row_pos: Optional[str] = None
    box_num: Optional[str] = None
    pcs_per_box: Optional[int] = None
    quantity: int = 0
    staff_name: Optional[str] = "Nandu"

class ItemResponse(ItemBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class StyleSummary(BaseModel):
    style: str
    total_quantity: int
    location_count: int
    sizes: List[str]
    colors: List[str]

class StockAdjustPayload(BaseModel):
    change_amount: int
    reason: Optional[str] = "Quick Floor Adjust"
    staff_name: Optional[str] = "Manager"
    movement_type: Optional[str] = "QUICK_ADJUST"

class SetQuantityPayload(BaseModel):
    new_quantity: int
    reason: Optional[str] = "Direct Count Update"
    staff_name: Optional[str] = "Manager"

class WarehouseStats(BaseModel):
    total_styles: int
    total_records: int
    total_units: int
    total_locations: int

class SheetRowItem(BaseModel):
    action: str = "IN"  # IN (Add/Receive), OUT (Deduct/Ship), SET (Exact Qty), DELETE (Remove Location)
    style: str
    color: Optional[str] = "STANDARD"
    size: Optional[str] = "OS"
    line: Optional[str] = None
    section: Optional[str] = None
    level: Optional[str] = None
    row_pos: Optional[str] = None
    box_num: Optional[str] = None      # Cartons / Box #
    pcs_per_box: Optional[int] = None  # Pcs per Carton
    quantity: int = 0                  # Total Pieces

class SheetSubmitPayload(BaseModel):
    rows: List[SheetRowItem]
    sheet_note: Optional[str] = "Manager Sheet Entry"
    staff_name: Optional[str] = "Nandu"

class BulkDeletePayload(BaseModel):
    item_ids: List[int]
    staff_name: Optional[str] = "Nandu"

class StyleRenamePayload(BaseModel):
    old_style: str
    new_style: str
    staff_name: Optional[str] = "Nandu"
