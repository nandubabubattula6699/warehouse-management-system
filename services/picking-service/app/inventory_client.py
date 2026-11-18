"""HTTP client for the Inventory service. The picking service never touches the database directly."""
from typing import Optional
import httpx

from app.config import INVENTORY_SERVICE_URL, INTERNAL_API_KEY


class InventoryError(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _internal_headers() -> dict:
    return {"X-Internal-Key": INTERNAL_API_KEY}


def _raise_for(resp: httpx.Response):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise InventoryError(resp.status_code, detail)


async def get_current_user(cookie_header: Optional[str], authorization: Optional[str]) -> Optional[dict]:
    """Ask the inventory service who the logged-in user is (forwarding their session)."""
    if not cookie_header and not authorization:
        return None
    headers = {}
    if cookie_header:
        headers["Cookie"] = cookie_header
    if authorization:
        headers["Authorization"] = authorization
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{INVENTORY_SERVICE_URL}/api/auth/me", headers=headers)
    if resp.status_code == 401:
        return None
    _raise_for(resp)
    return resp.json().get("user")


async def get_section_stock(warehouse_part: str, line: str, section: str) -> list:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{INVENTORY_SERVICE_URL}/api/internal/locations/stock",
            params={"warehouse_part": warehouse_part, "line": line, "section": section},
            headers=_internal_headers(),
        )
    _raise_for(resp)
    return resp.json().get("items", [])


async def pick(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{INVENTORY_SERVICE_URL}/api/internal/inventory/pick",
            json=payload,
            headers=_internal_headers(),
        )
    _raise_for(resp)
    return resp.json()
