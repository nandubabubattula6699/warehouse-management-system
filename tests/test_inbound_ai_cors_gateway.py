"""Phase 1a (e) AI reader, CORS, internal key, /scan gateway protection, inbound validation."""
import urllib.error

import pytest

import app.main as main_mod
from app import llm_parser


# ---------------------------------------------------------------- (e) AI document reader
def test_parse_docs_not_configured_returns_503_without_data(staff):
    r = staff.post("/api/inbound/parse-docs", json={"raw_text": "A12501 10 boxes"})
    assert r.status_code == 503
    body = r.json()
    assert "GEMINI_MODEL" in body["detail"]
    assert "data" not in body


def test_parse_docs_gemini_failure_returns_502(staff, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "some-model")

    def boom(*a, **k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(llm_parser.urllib.request, "urlopen", boom)
    r = staff.post("/api/inbound/parse-docs", json={"raw_text": "A12501"})
    assert r.status_code == 502
    assert "Nothing was extracted" in r.json()["detail"]


def test_parser_never_contains_sample_fallback():
    assert not hasattr(llm_parser, "_fallback_smart_parser")


def test_parse_docs_requires_a_document(staff, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "m")
    assert staff.post("/api/inbound/parse-docs", json={}).status_code == 400


def test_gemini_key_sent_in_header_not_url(monkeypatch):
    seen = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return (b'{"candidates":[{"content":{"parts":[{"text":"{\\"items\\":[{\\"style\\":\\"A1\\",'
                    b'\\"quantity\\":3}]}"}]}}]}')

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["key"] = req.get_header("X-goog-api-key")
        return FakeResp()

    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(llm_parser.urllib.request, "urlopen", fake_urlopen)
    out = llm_parser.parse_inbound_documents(raw_text="A1 x3")
    assert out["items"][0]["style"] == "A1"
    assert "secret-key" not in seen["url"]
    assert "gemini-test" in seen["url"]
    assert seen["key"] == "secret-key"


# ---------------------------------------------------------------- inbound validation
def test_shipment_line_without_style_rejected(staff):
    r = staff.post("/api/inbound/shipments", json={"items": [{"style": "  ", "quantity": 5}]})
    assert r.status_code == 400


def test_shipment_blank_line_numbers_accepted(staff):
    r = staff.post("/api/inbound/shipments", json={"items": [
        {"style": "A1", "box_count": None, "quantity": None, "pcs_per_box": None},
    ]})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- CORS
def test_cors_only_allows_configured_origin(anon):
    ok = anon.options("/api/health", headers={"Origin": "https://allowed.example",
                                               "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://allowed.example"
    bad = anon.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_cors_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        main_mod._allowed_origins()


# ---------------------------------------------------------------- internal API key
def test_internal_api_requires_correct_key(anon):
    path = "/api/internal/locations/stock?line=1&section=1"
    assert anon.get(path).status_code == 403
    assert anon.get(path, headers={"X-Internal-Key": "wh-internal-default-key-2026"}).status_code == 403
    assert anon.get(path, headers={"X-Internal-Key": "test-internal-key-0123456789"}).status_code == 200


# ---------------------------------------------------------------- /scan gateway
class _Capture:
    """Stand-in for httpx.AsyncClient that records the forwarded request."""
    last = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, params=None, headers=None, content=None):
        _Capture.last = {"method": method, "url": url, "headers": headers}

        class R:
            status_code = 200
            content = b"{}"
            headers = {"content-type": "application/json"}
        return R()


@pytest.fixture
def capture(monkeypatch):
    _Capture.last = None
    monkeypatch.setattr(main_mod.httpx, "AsyncClient", _Capture)
    return _Capture


def test_scan_train_blocked_for_anonymous_and_staff(anon, staff, capture):
    assert anon.post("/scan/api/train").status_code == 403
    assert staff.post("/scan/api/feedback", json={"raw_text": "x"}).status_code == 403
    assert capture.last is None  # never forwarded


def test_scan_train_forwarded_with_key_for_manager(manager, capture):
    r = manager.post("/scan/api/train", headers={"X-Internal-Key": "client-forged"})
    assert r.status_code == 200
    assert capture.last["headers"]["X-Internal-Key"] == "test-internal-key-0123456789"


def test_gateway_strips_client_supplied_internal_key(anon, capture):
    anon.post("/scan/api/analyze", headers={"X-Internal-Key": "client-forged"}, json={"raw_text": "x"})
    forwarded = {k.lower(): v for k, v in capture.last["headers"].items()}
    assert "x-internal-key" not in forwarded
