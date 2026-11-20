"""picking-service tests: no network, no database. The inventory service is replaced by fakes."""
import os

import pytest

os.environ["INTERNAL_API_KEY"] = "test-internal-key-0123456789"
os.environ["PICK_DEVICE_TOKENS"] = "scanner-1:tok-scanner-1-aaaaaaaaaaaaaaaaaaaa,scanner-2:tok-scanner-2-bbbbbbbbbbbbbbbbbbbb"
os.environ["PUBLIC_BASE_URL"] = "https://wh.example"

from fastapi.testclient import TestClient  # noqa: E402

from app import inventory_client  # noqa: E402
from app.main import app  # noqa: E402

GOOD = {"X-Device-Token": "tok-scanner-1-aaaaaaaaaaaaaaaaaaaa"}


@pytest.fixture
def fake_inventory(monkeypatch):
    calls = {"picks": []}

    async def get_section_stock(part, line, section):
        return [{"item_id": 1, "style": "A1", "color": "C", "size": "9", "level": "1", "quantity": 4}]

    async def pick(payload):
        calls["picks"].append(payload)
        return {"status": "ok", "picked": payload["quantity"], "style": payload["style"], "size": "9",
                "level": payload["level"], "quantity_after": 3}

    monkeypatch.setattr(inventory_client, "get_section_stock", get_section_stock)
    monkeypatch.setattr(inventory_client, "pick", pick)
    return calls


@pytest.fixture
def client():
    return TestClient(app)
