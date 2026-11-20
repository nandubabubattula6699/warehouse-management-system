"""
Picking Service (microservice)
------------------------------
QR-code based floor picking for all 14 Allbirds Lines and all 501 Sections.
No user login: floor staff scan the 4x6 Zebra QR code pasted on a rack section, enter or tap
the style, choose the level (1..4), and tap SAVE. The phone/scanner must be a REGISTERED DEVICE:
it sends its device token (X-Device-Token header, from PICK_DEVICE_TOKENS) with every stock
lookup and pick. The pick is sent to the Inventory service, which deducts stock and records an
audit movement that includes the device name.

Label pages, QR images and label PDFs stay public (they contain no stock data).

All routes live under /pick so the service works identically directly or behind the gateway.
"""
import hmac
import io
import os
from typing import Optional

import segno
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, JSONResponse
from pydantic import BaseModel, Field

from app import inventory_client
from app.config import (
    PICK_STATIONS,
    PICK_DEVICE_TOKENS,
    LINE_SECTION_COUNTS,
    PUBLIC_BASE_URL,
    MAX_PICK_QUANTITY,
    resolve_station,
)
from app.inventory_client import InventoryError
from app.pdf_generator import build_zebra_4x6_pdf

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="Warehouse OS - Picking Service",
    version="2.1.0",
    docs_url="/pick/docs",
    openapi_url="/pick/openapi.json",
)


# ----------------------------------------------------------------------------- helpers
def _station(code: str) -> dict:
    station = resolve_station(code)
    if not station:
        raise HTTPException(status_code=404, detail=f"Unknown or inactive pick station '{code}'.")
    return station


def _public_base(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}"


def _scan_url(request: Request, code: str) -> str:
    return f"{_public_base(request)}/pick/s/{code}"


DEVICE_TOKEN_HEADER = "X-Device-Token"


def require_device(request: Request) -> str:
    """Return the registered device name for the X-Device-Token header, or 401."""
    supplied = (request.headers.get(DEVICE_TOKEN_HEADER) or "").strip()
    if supplied:
        for token, device_name in PICK_DEVICE_TOKENS.items():
            if hmac.compare_digest(supplied.encode(), token.encode()):
                return device_name
    raise HTTPException(
        status_code=401,
        detail="This device is not registered for QR picking. Ask a supervisor for the device token.",
    )


# ----------------------------------------------------------------------------- health
@app.get("/pick/health")
async def health():
    return {
        "status": "ok",
        "service": "picking-service",
        "auth_required": "device_token",
        "total_lines": len(LINE_SECTION_COUNTS),
        "total_stations": len(PICK_STATIONS),
    }


# ----------------------------------------------------------------------------- pages (no login required)
@app.get("/pick/s/{code}", include_in_schema=False)
async def scan_page(code: str):
    """Page opened by scanning any section's QR code (no login required)."""
    _station(code)
    return FileResponse(os.path.join(STATIC_DIR, "pick.html"))


@app.get("/pick/labels", include_in_schema=False)
async def labels_hub_page():
    """Hub page to browse all 14 Lines / 501 Sections and download 4x6 Zebra PDFs."""
    return FileResponse(os.path.join(STATIC_DIR, "labels_hub.html"))


@app.get("/pick/labels/{code}", include_in_schema=False)
async def label_page(code: str):
    """Printable 4x6 QR label for a single station."""
    _station(code)
    return FileResponse(os.path.join(STATIC_DIR, "label.html"))


# ----------------------------------------------------------------------------- 4x6 Zebra PDF
@app.get("/pick/labels.pdf")
async def download_labels_pdf(
    request: Request,
    line: Optional[str] = Query(None, description="Optional Line number (1..14) to print a single Line"),
    code: Optional[str] = Query(None, description="Optional single station code e.g. P1-L1-S1"),
):
    """
    Generate and download a 4x6 inch Zebra thermal printer PDF containing:
      - All 501 QR labels across Lines 1..14 (default)
      - All sections for one Line (?line=1..14)
      - A single section label (?code=P1-L1-S1)
    """
    if code:
        st = _station(code)
        stations = [st]
        cache_key = f"CODE:{st['code']}"
        filename = f"Zebra_4x6_QR_{st['code']}.pdf"
    elif line:
        ln = str(line).strip()
        stations = [s for s in PICK_STATIONS.values() if s["line"] == ln]
        if not stations:
            raise HTTPException(status_code=404, detail=f"No sections found for Line '{ln}'.")
        cache_key = f"LINE:{ln}"
        filename = f"Zebra_4x6_QR_Allbirds_Line_{ln}_({len(stations)}_Labels).pdf"
    else:
        stations = list(PICK_STATIONS.values())
        cache_key = "ALL_501"
        filename = f"Zebra_4x6_QR_Allbirds_All_14_Lines_({len(stations)}_Labels).pdf"

    pdf_bytes = build_zebra_4x6_pdf(stations, _public_base(request), cache_key=cache_key)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ----------------------------------------------------------------------------- QR images
@app.get("/pick/qr/{code}.png")
async def qr_png(code: str, request: Request, scale: int = 12):
    st = _station(code)
    buf = io.BytesIO()
    segno.make(_scan_url(request, st["code"]), error="m").save(
        buf, kind="png", scale=max(4, min(scale, 30)), border=2
    )
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/pick/qr/{code}.svg")
async def qr_svg(code: str, request: Request):
    st = _station(code)
    buf = io.BytesIO()
    segno.make(_scan_url(request, st["code"]), error="m").save(buf, kind="svg", scale=10, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


# ----------------------------------------------------------------------------- API (no login required)
@app.get("/pick/api/stations")
async def list_all_stations(request: Request):
    base = _public_base(request)
    lines = [
        {
            "line": ln,
            "sections_count": sec_count,
            "pdf_url": f"/pick/labels.pdf?line={ln}",
            "sections": [
                {
                    "section": str(s),
                    "code": f"P1-L{ln}-S{s}",
                    "label_url": f"/pick/labels/P1-L{ln}-S{s}",
                    "scan_url": f"{base}/pick/s/P1-L{ln}-S{s}",
                    "qr_png": f"/pick/qr/P1-L{ln}-S{s}.png",
                }
                for s in range(1, sec_count + 1)
            ],
        }
        for ln, sec_count in LINE_SECTION_COUNTS.items()
    ]
    return {
        "total_lines": len(LINE_SECTION_COUNTS),
        "total_stations": len(PICK_STATIONS),
        "master_pdf_url": "/pick/labels.pdf",
        "lines": lines,
    }


@app.get("/pick/api/stations/{code}")
async def station_label_info(code: str, request: Request):
    """Public station details for printable labels (no stock data)."""
    station = _station(code)
    return {"station": station, "scan_url": _scan_url(request, station["code"])}


@app.get("/pick/api/s/{code}")
async def station_info(code: str, request: Request, device: str = Depends(require_device)):
    station = _station(code)
    try:
        items = await inventory_client.get_section_stock(
            station["warehouse_part"], station["line"], station["section"]
        )
    except InventoryError as e:
        raise HTTPException(status_code=502, detail=f"Inventory service error: {e.detail}")
    items = [i for i in items if str(i.get("level")) in station["levels"]]
    return {
        "station": station,
        "scan_url": _scan_url(request, station["code"]),
        "device": device,
        "items": items,
    }


class PickRequest(BaseModel):
    style: str = Field(..., min_length=1, max_length=100)
    level: str
    quantity: int = Field(1, ge=1)
    item_id: Optional[int] = None
    staff_name: Optional[str] = None


@app.post("/pick/api/s/{code}/picks")
async def create_pick(code: str, body: PickRequest, device: str = Depends(require_device)):
    station = _station(code)

    level = body.level.strip()
    if level not in station["levels"]:
        raise HTTPException(status_code=400, detail=f"Level must be one of {', '.join(station['levels'])}.")
    if body.quantity > MAX_PICK_QUANTITY:
        raise HTTPException(status_code=400, detail=f"Quantity cannot exceed {MAX_PICK_QUANTITY}.")

    # Audit name always carries the registered device, e.g. "Floor Staff (QR Scan) [scanner-1]".
    typed = (body.staff_name or "").strip()[:55] or "Floor Staff (QR Scan)"
    staff = f"{typed} [{device}]"

    try:
        result = await inventory_client.pick({
            "style": body.style.strip().upper(),
            "warehouse_part": station["warehouse_part"],
            "line": station["line"],
            "section": station["section"],
            "level": level,
            "quantity": body.quantity,
            "item_id": body.item_id,
            "staff_name": staff,
            "source": "QR_PICK",
        })
    except InventoryError as e:
        if e.status_code in (400, 404, 409):
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        raise HTTPException(status_code=502, detail=f"Inventory service error: {e.detail}")
    return result


@app.get("/pick", include_in_schema=False)
async def root():
    return RedirectResponse(url="/pick/labels", status_code=302)
