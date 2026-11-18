"""
Picking Service (microservice)
------------------------------
QR-code based floor picking for all 14 Allbirds Lines and all 501 Sections.
A worker scans the 4x6 Zebra QR code pasted on a rack section, enters or taps the style,
chooses the level (1..4), and taps SAVE. The pick is sent to the Inventory service,
which deducts stock and records an audit movement.

All routes live under /pick so the service works identically directly or behind the gateway.
"""
import io
import os
from typing import Optional

import segno
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, JSONResponse
from pydantic import BaseModel, Field

from app import inventory_client
from app.config import (
    PICK_STATIONS,
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
    version="2.0.0",
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


async def _user(request: Request) -> Optional[dict]:
    try:
        return await inventory_client.get_current_user(
            request.headers.get("cookie"), request.headers.get("authorization")
        )
    except InventoryError:
        return None
    except Exception:
        raise HTTPException(status_code=503, detail="Inventory service is unavailable.")


async def _require_user(request: Request) -> dict:
    user = await _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user


def _login_redirect(request: Request) -> RedirectResponse:
    q = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/login?next={request.url.path}{q}", status_code=302)


# ----------------------------------------------------------------------------- health
@app.get("/pick/health")
async def health():
    return {
        "status": "ok",
        "service": "picking-service",
        "total_lines": len(LINE_SECTION_COUNTS),
        "total_stations": len(PICK_STATIONS),
    }


# ----------------------------------------------------------------------------- pages
@app.get("/pick/s/{code}", include_in_schema=False)
async def scan_page(code: str, request: Request):
    """Page opened by scanning any section's QR code."""
    _station(code)
    if not await _user(request):
        return _login_redirect(request)
    return FileResponse(os.path.join(STATIC_DIR, "pick.html"))


@app.get("/pick/labels", include_in_schema=False)
async def labels_hub_page(request: Request):
    """Hub page to browse all 14 Lines / 501 Sections and download 4x6 Zebra PDFs."""
    user = await _user(request)
    if not user:
        return _login_redirect(request)
    if user.get("role") not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager can print QR labels.")
    return FileResponse(os.path.join(STATIC_DIR, "labels_hub.html"))


@app.get("/pick/labels/{code}", include_in_schema=False)
async def label_page(code: str, request: Request):
    """Printable 4x6 QR label for a single station (Admin / Manager only)."""
    _station(code)
    user = await _user(request)
    if not user:
        return _login_redirect(request)
    if user.get("role") not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager can print QR labels.")
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
    user = await _user(request)
    if not user:
        return _login_redirect(request)
    if user.get("role") not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager can download QR label PDFs.")

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


# ----------------------------------------------------------------------------- API
@app.get("/pick/api/stations")
async def list_all_stations(request: Request):
    user = await _require_user(request)
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
        "user": {"full_name": user.get("full_name"), "username": user.get("username"), "role": user.get("role")},
        "lines": lines,
    }


@app.get("/pick/api/s/{code}")
async def station_info(code: str, request: Request):
    station = _station(code)
    user = await _require_user(request)
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
        "user": {"full_name": user.get("full_name"), "username": user.get("username"), "role": user.get("role")},
        "items": items,
    }


class PickRequest(BaseModel):
    style: str = Field(..., min_length=1, max_length=100)
    level: str
    quantity: int = Field(1, ge=1)
    item_id: Optional[int] = None


@app.post("/pick/api/s/{code}/picks")
async def create_pick(code: str, body: PickRequest, request: Request):
    station = _station(code)
    user = await _require_user(request)

    level = body.level.strip()
    if level not in station["levels"]:
        raise HTTPException(status_code=400, detail=f"Level must be one of {', '.join(station['levels'])}.")
    if body.quantity > MAX_PICK_QUANTITY:
        raise HTTPException(status_code=400, detail=f"Quantity cannot exceed {MAX_PICK_QUANTITY}.")

    staff = user.get("full_name") or user.get("username") or "Unknown"
    if user.get("username"):
        staff = f"{staff} (@{user['username']})"

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
