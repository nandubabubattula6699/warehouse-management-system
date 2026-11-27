"""Part 2 locations step E: Zebra label PDF (one spot / one row / all) and scan lookup by code."""
import pytest

from app.location_labels import (PRINTER_DOT, barcode_bar_width, describe, label_settings, normalize_scan,
                                 qr_content)
from app.models import InventoryItem, Location
from tests.conftest import _logged_in, make_user


@pytest.fixture
def spots(db):
    uid = make_user(db, "lbladmin", role="ADMIN").id
    rows = [
        ("R3-S5-L2", "STORAGE", "SHELF", 3, 5, 2), ("R3-S5-L1", "STORAGE", "SHELF", 3, 5, 1),
        ("R3-GF-L1", "STORAGE", "GROUND_FRONT", 3, None, 1), ("R4-S1-L1", "STORAGE", "SHELF", 4, 1, 1),
        ("W-SB-L2", "STORAGE", "WALL_BACK", None, None, 2), ("R-RECV", "RECEIVING", None, None, None, None),
    ]
    for code, t, area, r, s, lv in rows:
        db.add(Location(code=code, location_type=t, area=area, row_no=r, section_no=s, level_no=lv, created_by=uid))
    old = Location(code="R9-S9-L9", location_type="STORAGE", area="SHELF", row_no=9, section_no=9, level_no=9,
                   created_by=uid, is_active=False)
    db.add(old)
    db.commit()
    return {loc.code: loc for loc in db.query(Location)}


def _pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") or pdf.count(b"/Type /Page ") or pdf.count(b"/Type /Page>")


def test_settings_default_and_override(monkeypatch):
    for var in ("LOCATION_LABEL_SIZE", "LOCATION_LABEL_QR", "LOCATION_LABEL_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert label_settings() == (4.0, 6.0, "{base}/loc/{code}", "https://alexander-warehouse.up.railway.app")
    monkeypatch.setenv("LOCATION_LABEL_SIZE", "3x2")
    monkeypatch.setenv("LOCATION_LABEL_QR", "{code}")
    monkeypatch.setenv("LOCATION_LABEL_BASE_URL", "https://wms.example.com/")
    assert label_settings() == (3.0, 2.0, "{code}", "https://wms.example.com")
    monkeypatch.setenv("LOCATION_LABEL_SIZE", "nonsense")
    monkeypatch.setenv("LOCATION_LABEL_QR", "no placeholder")
    assert label_settings()[:3] == (4.0, 6.0, "{base}/loc/{code}")


def test_qr_content_and_scan_normalizing():
    assert qr_content("{base}/loc/{code}", "https://wms.example.com/", "R3-S5-L2") == "https://wms.example.com/loc/R3-S5-L2"
    assert qr_content("{code}", "https://x", "W-SB-L2") == "W-SB-L2"
    assert normalize_scan("https://wms.example.com/loc/R3-S5-L2") == "R3-S5-L2"
    assert normalize_scan(" r3-s5-l2 ") == "R3-S5-L2"
    assert normalize_scan("/loc/W-SB-L2/") == "W-SB-L2"
    assert normalize_scan("W-SB-L2") == "W-SB-L2"  # Code 128 barcode = the plain code


@pytest.mark.parametrize("code", ["R3-S5-L2", "R12-S34-L4", "R-RECV"])
@pytest.mark.parametrize("width_pt", [288 - 26, 150])  # 4x6 inner width, 4x2 right column
def test_barcode_bars_are_whole_printer_dots_and_fit(code, width_pt):
    from reportlab.graphics.barcode.code128 import Code128
    bw = barcode_bar_width(code, width_pt)
    dots = bw / PRINTER_DOT
    assert abs(dots - round(dots)) < 1e-9 and dots >= 2
    assert Code128(code, barWidth=bw, quiet=False).width + 20 * bw <= width_pt or dots == 2


def test_describe(spots):
    assert describe(spots["R3-S5-L2"]) == "Row 3 · Shelf · Section 5 · Level 2"
    assert describe(spots["R3-GF-L1"]) == "Row 3 · Ground front · Level 1"
    assert describe(spots["W-SB-L2"]) == "Wall back · Level 2"
    assert describe(spots["R-RECV"]) == "Receiving"


@pytest.mark.parametrize("qs,pages", [("code=R3-S5-L2", 1), ("code=https://x/loc/r3-s5-l2", 1), ("row=3", 3),
                                      ("row=WALL", 1), ("row=SPECIAL", 1), ("all=true", 6)])
def test_label_pdf(manager, spots, monkeypatch, qs, pages):
    monkeypatch.delenv("LOCATION_LABEL_SIZE", raising=False)
    r = manager.get(f"/api/locations/labels.pdf?{qs}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert _pages(r.content) == pages
    assert "4x6in" in r.headers["content-disposition"]
    assert b"/MediaBox [ 0 0 288 432 ]" in r.content  # 4 x 6 inch portrait


def test_label_size_follows_the_setting(manager, spots, monkeypatch):
    monkeypatch.setenv("LOCATION_LABEL_SIZE", "4x2")
    r = manager.get("/api/locations/labels.pdf?row=3")
    assert r.status_code == 200 and b"/MediaBox [ 0 0 288 144 ]" in r.content and _pages(r.content) == 3


@pytest.mark.parametrize("qs,status", [("", 400), ("code=R3-S5-L2&all=true", 400), ("row=X1", 400),
                                       ("code=R9-S9-L9", 404), ("code=R1-S1-L1", 404)])
def test_label_pdf_refuses_bad_or_empty_requests(manager, spots, qs, status):
    assert manager.get(f"/api/locations/labels.pdf?{qs}").status_code == status


def test_labels_need_a_supervisor(staff, spots):
    assert staff.get("/api/locations/labels.pdf?all=true").status_code == 403


def test_lookup_shows_part2_stock_at_the_spot(staff, db, spots):
    db.add_all([
        InventoryItem(style="VDBP-039", color="CAMO", size="OS", row_pos="3", section="5", level="2",
                      warehouse_part="PART_2", location="Row 3 • Sec 5 • Lvl 2", quantity=24, pcs_per_box=8),
        InventoryItem(style="VOSB-030", color="BLACK", size="OS", row_pos="3", section="5", level="2",
                      warehouse_part="PART_2", location="Row 3 • Sec 5 • Lvl 2", quantity=0, pcs_per_box=10),
        InventoryItem(style="OLD", row_pos="3", section="5", level="2", warehouse_part="PART_2",
                      location="Row 3 • Sec 5 • Lvl 2", quantity=0, is_active=False),
        InventoryItem(style="NEXT", row_pos="3", section="5", level="1", warehouse_part="PART_2",
                      location="Row 3 • Sec 5 • Lvl 1", quantity=5),
        InventoryItem(style="TB1WJBK", line="3", section="5", level="2", warehouse_part="PART_1",
                      location="Line 3 • Sec 5 • Lvl 2", quantity=20),
    ])
    db.commit()
    r = staff.get("/api/locations/lookup", params={"q": "https://wms.example.com/loc/R3-S5-L2"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"] == "R3-S5-L2" and d["active"] is True and d["description"].startswith("Row 3")
    assert (d["rows"], d["pieces"]) == (2, 24)
    assert [i["style"] for i in d["items"]] == ["VDBP-039", "VOSB-030"]


def test_lookup_ground_and_wall_and_unknown(staff, db, spots):
    db.add_all([
        InventoryItem(style="G1", row_pos="3", section="FRONT", level="1", warehouse_part="PART_2",
                      location="Row 3 • Ground FRONT • Lvl 1", quantity=7),
        InventoryItem(style="W1", row_pos="WALL", section="BACK", level="2", warehouse_part="PART_2",
                      location="WALL • Lvl 2", quantity=9),
    ])
    db.commit()
    assert staff.get("/api/locations/lookup", params={"q": "r3-gf-l1"}).json()["pieces"] == 7
    assert staff.get("/api/locations/lookup", params={"q": "W-SB-L2"}).json()["pieces"] == 9
    assert staff.get("/api/locations/lookup", params={"q": "R1-S1-L1"}).status_code == 404


def test_lookup_needs_login(anon, spots):
    assert anon.get("/api/locations/lookup", params={"q": "R3-S5-L2"}).status_code == 401
    page = anon.get("/loc/R3-S5-L2", follow_redirects=False)
    assert page.status_code == 302 and page.headers["location"] == "/login?next=/loc/R3-S5-L2"


def test_lookup_page_is_served_after_login(db, spots):
    client = _logged_in(db, "floor1", "STAFF")
    assert client.get("/loc/R3-S5-L2").status_code == 200
    assert client.get("/loc").status_code == 200
