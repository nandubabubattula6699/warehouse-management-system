"""HTTP client for fetching live warehouse catalog and stock locations from the Inventory service."""
from typing import Dict, List, Optional
import httpx

from app.config import INVENTORY_SERVICE_URL, INTERNAL_API_KEY


def _headers() -> dict:
    return {"X-Internal-Key": INTERNAL_API_KEY}


def fetch_live_catalog_sync(timeout: float = 10.0) -> Optional[dict]:
    """Fetch live warehouse catalog (styles, colors, sizes, pcs_per_box) synchronously."""
    if not INTERNAL_API_KEY:
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{INVENTORY_SERVICE_URL}/api/internal/catalog", headers=_headers())
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


async def lookup_style_locations(style: str, color: Optional[str] = None) -> List[dict]:
    """Look up live warehouse rack locations and stock for a scanned style."""
    if not style or not INTERNAL_API_KEY:
        return []
    params = {"style": style}
    if color:
        params["color"] = color
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"{INVENTORY_SERVICE_URL}/api/internal/styles/lookup",
                params=params,
                headers=_headers(),
            )
            if resp.status_code == 200:
                return resp.json().get("items", [])
    except Exception:
        pass
    return []
