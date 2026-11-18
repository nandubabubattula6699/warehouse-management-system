import os
import re
from collections import OrderedDict
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Inventory service (the existing Warehouse OS app). It owns inventory data + user logins.
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8000").rstrip("/")

# Shared secret for service-to-service calls (must match INTERNAL_API_KEY on the inventory service).
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "wh-internal-default-key-2026")

# Public URL encoded into QR codes. If empty, it is derived from the gateway's forwarded headers.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

MAX_PICK_QUANTITY = int(os.getenv("MAX_PICK_QUANTITY", "500"))

# Exact section counts per Allbirds Line (Lines 1..14) matching live warehouse layout (501 sections total)
LINE_SECTION_COUNTS = OrderedDict([
    ("1", 40),
    ("2", 36),
    ("3", 36),
    ("4", 36),
    ("5", 36),
    ("6", 35),
    ("7", 35),
    ("8", 37),
    ("9", 37),
    ("10", 37),
    ("11", 34),
    ("12", 34),
    ("13", 34),
    ("14", 34),
])


def make_station(line: str, section: str) -> dict:
    ln = str(line).strip()
    sec = str(section).strip()
    code = f"P1-L{ln}-S{sec}"
    return {
        "code": code,
        "label": f"Allbirds • Line {ln} • Section {sec}",
        "brand": "ALLBIRDS",
        "warehouse_part": "PART_1",
        "line": ln,
        "section": sec,
        "levels": ["1", "2", "3", "4"],
        "qr_mounted_on_level": "1",
    }


# Master dictionary of all 501 Allbirds Line/Section QR stations in order
PICK_STATIONS: "OrderedDict[str, dict]" = OrderedDict()
for _ln, _max_sec in LINE_SECTION_COUNTS.items():
    for _s in range(1, _max_sec + 1):
        _st = make_station(_ln, str(_s))
        PICK_STATIONS[_st["code"]] = _st

_STATION_RE = re.compile(r"^P1-L(\d{1,2})-S(\d{1,2})$", re.IGNORECASE)


def resolve_station(code: str) -> Optional[dict]:
    """Return station config for any P1-L{line}-S{section} code."""
    key = (code or "").strip().upper()
    if key in PICK_STATIONS:
        return PICK_STATIONS[key]
    m = _STATION_RE.match(key)
    if m:
        ln_num, sec_num = int(m.group(1)), int(m.group(2))
        if 1 <= ln_num <= 14 and 1 <= sec_num <= 50:
            return make_station(str(ln_num), str(sec_num))
    return None
