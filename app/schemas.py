from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

class ItemBase(BaseModel):
    style: str
    brand: Optional[str] = "ALLBIRDS"
    warehouse_part: Optional[str] = "PART_1"
    placement_type: Optional[str] = "RACK"
    location_code: Optional[str] = None
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


class ReceivingPayload(BaseModel):
    style: str
    brand: Optional[str] = "ALLBIRDS"
    warehouse_part: Optional[str] = "PART_1"
    color: str = "STANDARD"
    size: str = "OS"
    line: Optional[str] = None
    row_pos: Optional[str] = None
    section: Optional[str] = None
    level: Optional[str] = None
    box_num: Optional[str] = None
    pcs_per_box: Optional[int] = None
    quantity: int = Field(..., gt=0)
    po_number: Optional[str] = None
    notes: Optional[str] = None
    staff_name: Optional[str] = "Warehouse Manager"


# ================= INBOUND SHIPMENT & MULTI-PALLET RECEIVING SCHEMAS =================
class InboundItemPayload(BaseModel):
    style: str
    brand: Optional[str] = "ALLBIRDS"
    warehouse_part: Optional[str] = "PART_1"
    color: str = "STANDARD"
    size: str = "OS"
    line: Optional[str] = None
    row_pos: Optional[str] = None
    section: Optional[str] = None
    level: Optional[str] = None
    box_num: Optional[str] = None
    box_count: int = 1
    pcs_per_box: Optional[int] = None
    quantity: int = 0
    expected_quantity: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None

class InboundItemResponse(InboundItemPayload):
    id: int
    shipment_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class InboundShipmentCreate(BaseModel):
    shipment_number: Optional[str] = None
    po_number: Optional[str] = None
    carrier_vendor: Optional[str] = None
    pallets_count: int = 1
    total_boxes: Optional[int] = 0
    total_units: Optional[int] = 0
    packing_list_filename: Optional[str] = None
    packing_list_data: Optional[str] = None
    commercial_invoice_filename: Optional[str] = None
    commercial_invoice_data: Optional[str] = None
    ai_extracted_raw: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = "Warehouse Manager"
    items: List[InboundItemPayload] = []

class InboundShipmentResponse(BaseModel):
    id: int
    shipment_number: str
    po_number: Optional[str] = None
    carrier_vendor: Optional[str] = None
    pallets_count: int = 1
    total_boxes: int = 0
    total_units: int = 0
    status: str = "PENDING_APPROVAL"
    packing_list_filename: Optional[str] = None
    packing_list_data: Optional[str] = None
    commercial_invoice_filename: Optional[str] = None
    commercial_invoice_data: Optional[str] = None
    ai_extracted_raw: Optional[str] = None
    notes: Optional[str] = None
    created_by: str = "Warehouse Manager"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[InboundItemResponse] = []
    model_config = ConfigDict(from_attributes=True)

class InboundParseRequest(BaseModel):
    packing_list_data: Optional[str] = None
    commercial_invoice_data: Optional[str] = None
    packing_list_filename: Optional[str] = None
    commercial_invoice_filename: Optional[str] = None
    raw_text: Optional[str] = None

class InboundApprovePayload(BaseModel):
    approved_by: Optional[str] = "Nandu (Admin)"
    notes: Optional[str] = None

class InboundRejectPayload(BaseModel):
    rejected_by: Optional[str] = "Nandu (Admin)"
    reason: str
