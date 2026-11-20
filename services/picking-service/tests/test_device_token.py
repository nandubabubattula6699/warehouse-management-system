"""Phase 1a (g): QR picking requires a registered device token; labels stay public."""
import pytest

from app import config
from tests.conftest import GOOD


def test_stock_lookup_requires_token(client, fake_inventory):
    assert client.get("/pick/api/s/P1-L1-S1").status_code == 401
    assert client.get("/pick/api/s/P1-L1-S1", headers={"X-Device-Token": "wrong"}).status_code == 401
    r = client.get("/pick/api/s/P1-L1-S1", headers=GOOD)
    assert r.status_code == 200
    assert r.json()["device"] == "scanner-1"


def test_pick_requires_token_and_records_device(client, fake_inventory):
    body = {"style": "a1", "level": "1", "quantity": 1, "staff_name": "Maria"}
    assert client.post("/pick/api/s/P1-L1-S1/picks", json=body).status_code == 401
    assert fake_inventory["picks"] == []
    r = client.post("/pick/api/s/P1-L1-S1/picks", json=body, headers=GOOD)
    assert r.status_code == 200, r.text
    sent = fake_inventory["picks"][0]
    assert sent["staff_name"] == "Maria [scanner-1]"
    assert sent["style"] == "A1"


def test_pick_without_name_still_records_device(client, fake_inventory):
    r = client.post("/pick/api/s/P1-L1-S1/picks", json={"style": "A1", "level": "1", "quantity": 1},
                    headers={"X-Device-Token": "tok-scanner-2-bbbbbbbbbbbbbbbbbbbb"})
    assert r.status_code == 200
    assert fake_inventory["picks"][0]["staff_name"] == "Floor Staff (QR Scan) [scanner-2]"


def test_labels_and_station_info_stay_public(client):
    assert client.get("/pick/api/stations/P1-L1-S1").status_code == 200
    assert "items" not in client.get("/pick/api/stations/P1-L1-S1").json()
    assert client.get("/pick/qr/P1-L1-S1.png").status_code == 200
    assert client.get("/pick/labels.pdf?code=P1-L1-S1").status_code == 200
    assert client.get("/pick/health").json()["auth_required"] == "device_token"


@pytest.mark.parametrize("raw", [
    "",                                   # missing
    "scanner-1",                          # no token
    "scanner-1:short",                    # too short
    "a:" + "x" * 30 + ",b:" + "x" * 30,   # duplicate token
])
def test_bad_device_token_config_refused(raw):
    with pytest.raises(RuntimeError):
        config._parse_device_tokens(raw)


def test_no_default_internal_key():
    src = open(config.__file__, encoding="utf-8").read()
    assert "wh-internal-default-key" not in src
