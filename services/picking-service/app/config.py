import os
from dotenv import load_dotenv

load_dotenv()

# Inventory service (the existing Warehouse OS app). It owns inventory data + user logins.
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8000").rstrip("/")

# Shared secret for service-to-service calls (must match INTERNAL_API_KEY on the inventory service).
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "wh-internal-default-key-2026")

# Public URL encoded into QR codes. If empty, it is derived from the gateway's forwarded headers.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# ---------------------------------------------------------------------------------------
# QR pick stations. One QR code per Line/Section; the worker chooses the level after scanning.
# Pilot: Allbirds (Part 1) Line 1 / Section 1 only. Add more entries here to roll out.
# ---------------------------------------------------------------------------------------
PICK_STATIONS = {
    "P1-L1-S1": {
        "code": "P1-L1-S1",
        "label": "Allbirds • Line 1 • Section 1",
        "brand": "ALLBIRDS",
        "warehouse_part": "PART_1",
        "line": "1",
        "section": "1",
        "levels": ["1", "2", "3", "4"],
        "qr_mounted_on_level": "1",
    },
}

MAX_PICK_QUANTITY = int(os.getenv("MAX_PICK_QUANTITY", "500"))
