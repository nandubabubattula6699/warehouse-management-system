"""
Picking Service (microservice)
------------------------------
QR-code based floor picking. A worker scans the QR code on a rack section, enters the style,
chooses the level, and saves. The pick is sent to the Inventory service, which deducts stock
and records an audit movement.

All routes live under /pick so the service works the same directly or behind the gateway.
"""
import io
import os
from typing import Optional

import segno
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, JSONResponse
from pydantic import BaseModel, Field

from app import inventory_client
from app.config import PICK_STATIONS, PUBLIC_BASE_URL, MAX_PICK_QUANTITY
from app.inventory_client import InventoryError

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Warehouse OS - Picking Service", version="1.0.0", docs_url="/pick/docs", openapi_url="/pick/openapi.json")


# ----------------------------------------------------------------------------- helpers
def _station(code: str) -> dict:
    station = PICK_STATIONS.get(code.upper())
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
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=302)


# ----------------------------------------------------------------------------- health
@app.get("/pick/health")
async def health():
    return {"status": "ok", "service": "picking-service", "stations": list(PICK_STATIONS.keys())}


# ----------------------------------------------------------------------------- pages
@app.get("/pick/s/{code}", include_in_schema=False)
async def scan_page(code: str, request: Request):
    """Page opened by scanning the QR code."""
    _station(code)
    if not await _user(request):
        return _login_redirect(request)
    return FileResponse(os.path.join(STATIC_DIR, "pick.html"))


@app.get("/pick/labels/{code}", include_in_schema=False)
async def label_page(code: str, request: Request):
    """Printable QR label for a station (Admin / Manager only)."""
    _station(code)
    user = await _user(request)
    if not user:
        return _login_redirect(request)
    if user.get("role") not in ("ADMIN", "MANAGER"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager can print QR labels.")
    return FileResponse(os.path.join(STATIC_DIR, "label.html"))


# ----------------------------------------------------------------------------- QR images
@app.get("/pick/qr/{code}.png")
async def qr_png(code: str, request: Request, scale: int = 12):
    _station(code)
    buf = io.BytesIO()
    segno.make(_scan_url(request, code), error="h").save(buf, kind="png", scale=max(4, min(scale, 30)), border=2)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/pick/qr/{code}.svg")
async def qr_svg(code: str, request: Request):
    _station(code)
    buf = io.BytesIO()
    segno.make(_scan_url(request, code), error="h").save(buf, kind="svg", scale=10, border=2)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


# ----------------------------------------------------------------------------- API
@app.get("/pick/api/s/{code}")
async def station_info(code: str, request: Request):
    station = _station(code)
    user = await _require_user(request)
    try:
        items = await inventory_client.get_section_stock(station["warehouse_part"], station["line"], station["section"])
    except InventoryError as e:
        raise HTTPException(status_code=502, detail=f"Inventory service error: {e.detail}")
    items = [i for i in items if str(i.get("level")) in station["levels"]]
    return {
        "station": station,
        "scan_url": _scan_url(request, code),
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
        # Pass business errors (not found / choose size / not enough stock) straight to the UI.
        if e.status_code in (400, 404, 409):
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        raise HTTPException(status_code=502, detail=f"Inventory service error: {e.detail}")
    return result


@app.get("/pick", include_in_schema=False)
async def root():
    return RedirectResponse(url="/", status_code=302)
