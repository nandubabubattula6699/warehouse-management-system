"""
Part 2 location labels (Zebra thermal PDF, one label per page) and code lookup helpers.

Settings (environment variables):
  LOCATION_LABEL_SIZE      label size in inches "WIDTHxHEIGHT". Default "4x6" (portrait, same roll as Allbirds).
                           "4x2" gives a compact landscape label.
  LOCATION_LABEL_QR        what the QR holds; "{code}" is the location code and "{base}" the WMS address.
                           Default "{base}/loc/{code}" (a link ending with the code); "{code}" alone = plain code.
  LOCATION_LABEL_BASE_URL  the WMS address used for "{base}". Default: production, https://alexander-warehouse.up.railway.app
Every label carries the code three ways: printed large (to read and type), a QR (phone camera) and a Code 128
barcode of the code only (scanner gun). The lookup page accepts all three: QR link, plain code, typed code.
"""
import io
import math
import os
import re

import segno
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DEFAULT_SIZE = "4x6"
DEFAULT_QR = "{base}/loc/{code}"
DEFAULT_BASE_URL = "https://alexander-warehouse.up.railway.app"
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*$")
AREA_TEXT = {"SHELF": "Shelf", "GROUND_FRONT": "Ground front", "GROUND_BACK": "Ground back",
             "WALL_FRONT": "Wall front", "WALL_BACK": "Wall back"}
SPECIAL_TEXT = {"RECEIVING": "Receiving", "STAGING": "Staging", "DAMAGE": "Damaged goods"}

PRINTER_DOT = 72.0 / 203.0       # one dot of a 203 dpi Zebra, in points: bars are whole dots wide
BARCODE_QUIET_MODULES = 10       # Code 128 needs a clear zone of 10 bar widths on each side


def label_settings():
    """(width_in, height_in, qr_template, base_url) from the environment, validated."""
    m = _SIZE_RE.match(os.getenv("LOCATION_LABEL_SIZE") or DEFAULT_SIZE)
    width, height = (float(m.group(1)), float(m.group(2))) if m else (4.0, 6.0)
    if not (1.5 <= width <= 8.0 and 1.0 <= height <= 8.0):
        width, height = 4.0, 6.0
    qr = os.getenv("LOCATION_LABEL_QR") or DEFAULT_QR
    if "{code}" not in qr:
        qr = DEFAULT_QR
    base = (os.getenv("LOCATION_LABEL_BASE_URL") or "").strip().rstrip("/") or DEFAULT_BASE_URL
    return width, height, qr, base


def qr_content(template: str, base: str, code: str) -> str:
    return template.replace("{base}", base.rstrip("/")).replace("{code}", code)


def normalize_scan(raw: str) -> str:
    """A scanned or typed value -> location code: QR link / path ending with the code, barcode or typed code."""
    value = (raw or "").strip().rstrip("/")
    return value.rsplit("/", 1)[-1].strip().upper()


def describe(loc) -> str:
    if loc.location_type != "STORAGE":
        return SPECIAL_TEXT.get(loc.location_type, loc.location_type.title())
    parts = [] if loc.row_no is None else [f"Row {loc.row_no}"]
    parts.append(AREA_TEXT.get(loc.area, loc.area))
    if loc.section_no is not None:
        parts.append(f"Section {loc.section_no}")
    parts.append(f"Level {loc.level_no}")
    return " · ".join(parts)


def _draw_qr(c, data: str, x0: float, y0: float, size: float):
    q = segno.make(data, error="m")
    matrix = q.matrix
    n = len(matrix)
    cell = size / float(n)
    p = c.beginPath()
    for r_idx, row in enumerate(matrix):
        y = y0 + (n - 1 - r_idx) * cell
        c_idx = 0
        while c_idx < n:
            if row[c_idx]:
                start = c_idx
                while c_idx < n and row[c_idx]:
                    c_idx += 1
                p.rect(x0 + start * cell, y, (c_idx - start) * cell + 0.04, cell + 0.04)
            else:
                c_idx += 1
    c.setFillColor(colors.black)
    c.drawPath(p, stroke=0, fill=1)


def barcode_bar_width(code: str, available: float) -> float:
    """Narrowest-bar width in points: whole printer dots, as wide as fits with the quiet zones, at least 2 dots."""
    modules = Code128(code, barWidth=1, quiet=False).width
    dots = math.floor(available / (modules + 2 * BARCODE_QUIET_MODULES) / PRINTER_DOT)
    return max(2, min(dots, 6)) * PRINTER_DOT


def _draw_barcode(c, code: str, center_x: float, y: float, available: float, height: float):
    bw = barcode_bar_width(code, available)
    bc = Code128(code, barWidth=bw, barHeight=height, quiet=False)
    bc.drawOn(c, center_x - bc.width / 2.0, y)


def _fit(text: str, font: str, max_width: float, start: float, smallest: float) -> float:
    size = start
    while size > smallest and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _centered(c, text, font, size, x, y):
    c.setFont(font, size)
    c.drawCentredString(x, y, text)


def _draw_portrait(c, loc, qr_data, W, H):
    """4x6 style: code on top, description, PART 2, a line, big QR, then the Code 128 barcode at the bottom."""
    m = 0.18 * inch
    cx = W / 2.0
    inner = W - 2 * m
    y = H - m
    code_size = _fit(loc.code, "Helvetica-Bold", inner, start=H * 0.14, smallest=14)
    y -= code_size * 0.82
    c.setFillColor(colors.black)
    _centered(c, loc.code, "Helvetica-Bold", code_size, cx, y)
    desc = describe(loc)
    desc_size = _fit(desc, "Helvetica", inner, start=H * 0.042, smallest=8)
    y -= desc_size * 1.7
    _centered(c, desc, "Helvetica", desc_size, cx, y)
    tag = "PART 2" + ("" if loc.is_active else " · DEACTIVATED")
    tag_size = H * 0.036
    y -= tag_size * 1.5
    _centered(c, tag, "Helvetica-Bold", tag_size, cx, y)
    y -= tag_size * 0.9
    c.setLineWidth(1.5)
    c.line(m, y, W - m, y)

    note_size = max(7.0, H * 0.026)
    bar_h = H * 0.12
    bottom_text = note_size * 1.2 + max(9.0, H * 0.03) * 1.25
    bar_y = m + bottom_text + note_size * 0.6
    qr_top = y - 0.12 * inch
    qr_bottom_limit = bar_y + bar_h + note_size * 2.6
    qr_size = min(inner * 0.86, qr_top - qr_bottom_limit - note_size * 1.6)
    qr_y = qr_top - qr_size
    _draw_qr(c, qr_data, cx - qr_size / 2.0, qr_y, qr_size)
    _centered(c, "QR: phone camera", "Helvetica", note_size, cx, qr_y - note_size * 1.4)

    _draw_barcode(c, loc.code, cx, bar_y, inner, bar_h)
    code_txt = max(9.0, H * 0.03)
    _centered(c, loc.code, "Helvetica-Bold", code_txt, cx, bar_y - code_txt * 1.1)
    _centered(c, "Barcode: scanner gun", "Helvetica", note_size, cx, bar_y - code_txt * 1.1 - note_size * 1.3)


def _draw_landscape(c, loc, qr_data, W, H):
    """4x2 style: QR on the left; code, description, PART 2 and the Code 128 barcode on the right."""
    m = 0.12 * inch
    qr_size = min(H - 2 * m, W * 0.38)
    _draw_qr(c, qr_data, m, (H - qr_size) / 2.0, qr_size)
    x = m + qr_size + 0.14 * inch
    col = W - x - m
    cx = x + col / 2.0
    c.setFillColor(colors.black)
    code_size = _fit(loc.code, "Helvetica-Bold", col, start=H * 0.26, smallest=10)
    y = H - m - code_size * 0.8
    _centered(c, loc.code, "Helvetica-Bold", code_size, cx, y)
    desc = describe(loc)
    desc_size = _fit(desc, "Helvetica", col, start=max(6.5, H * 0.075), smallest=5.5)
    y -= desc_size * 1.6
    _centered(c, desc, "Helvetica", desc_size, cx, y)
    tag_size = max(6.0, H * 0.06)
    y -= tag_size * 1.4
    _centered(c, "PART 2" + ("" if loc.is_active else " · DEACTIVATED"), "Helvetica-Bold", tag_size, cx, y)
    note = max(5.5, H * 0.045)
    bar_y = m + note * 1.3
    bar_h = max(0.25 * inch, y - tag_size * 0.9 - bar_y - 2)
    _draw_barcode(c, loc.code, cx, bar_y, col, bar_h)
    _centered(c, "Barcode: scanner gun · QR: phone camera", "Helvetica", note, cx, m)


def build_labels_pdf(locations, base_url: str, width_in: float, height_in: float, qr_template: str) -> bytes:
    """One label per page, black on white. Portrait sizes get the 4x6 layout, landscape sizes the compact one."""
    W, H = width_in * inch, height_in * inch
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Alexander Warehouse - Part 2 location labels")
    c.setAuthor("Alexander Warehouse OS")
    draw = _draw_portrait if H >= W else _draw_landscape
    for loc in locations:
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        draw(c, loc, qr_content(qr_template, base_url, loc.code), W, H)
        c.showPage()
    c.save()
    return buf.getvalue()


def label_order(loc):
    """Walking-friendly print order: rows 1.., then wall, then special spots; shelf by section and level."""
    area_rank = {"SHELF": 0, "GROUND_FRONT": 1, "GROUND_BACK": 2, "WALL_FRONT": 3, "WALL_BACK": 4}
    special = loc.location_type != "STORAGE"
    return (special, loc.row_no is None, loc.row_no or 0, area_rank.get(loc.area, 9), loc.section_no or 0,
            loc.level_no or 0, loc.code)
