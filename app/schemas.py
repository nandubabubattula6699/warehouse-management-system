from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

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

class ItemResponse(ItemBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

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
