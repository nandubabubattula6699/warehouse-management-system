"""
4x6 Inch Zebra Thermal Label PDF Generator
------------------------------------------
Generates multi-page 4" x 6" (288pt x 432pt) vector QR code labels ready for Zebra 4x6 label printers.
Each page is one section's QR code label (Allbirds Lines 1..14, all 501 sections).
"""
import io
from typing import Dict, List, Tuple
import segno
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors

_PDF_CACHE: Dict[Tuple[str, str], bytes] = {}


def _draw_qr_matrix(c: canvas.Canvas, url: str, x0: float, y0: float, size: float):
    q = segno.make(url, error="m")
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


def build_zebra_4x6_pdf(stations: List[dict], base_url: str, cache_key: str = "ALL") -> bytes:
    """
    Build a 4" x 6" multi-page PDF with 1 high-contrast vector QR label per page.
    Cached in memory by (base_url, cache_key) for instant repeat downloads.
    """
    base = base_url.rstrip("/")
    key = (base, cache_key)
    if key in _PDF_CACHE:
        return _PDF_CACHE[key]

    W = 4.0 * inch  # 288 pt
    H = 6.0 * inch  # 432 pt
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Alexander Warehouse - Allbirds 4x6 Zebra QR Labels")
    c.setAuthor("Alexander Warehouse OS")

    total = len(stations)
    qr_size = 2.45 * inch
    qr_x = (W - qr_size) / 2.0
    qr_y = 124.0

    for idx, st in enumerate(stations, start=1):
        code = st["code"]
        line_num = st["line"]
        sec_num = st["section"]
        scan_url = f"{base}/pick/s/{code}"

        # Outer thick border
        c.setStrokeColor(colors.black)
        c.setFillColor(colors.white)
        c.setLineWidth(2.5)
        c.roundRect(10, 10, W - 20, H - 20, 8, stroke=1, fill=1)

        # Top black header block
        c.setFillColor(colors.black)
        c.roundRect(10, H - 56, W - 20, 46, 8, stroke=0, fill=1)
        c.rect(10, H - 56, W - 20, 12, stroke=0, fill=1)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11.5)
        c.drawCentredString(W / 2.0, H - 30, "ALEXANDER WAREHOUSE OS")
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(W / 2.0, H - 45, "PART 1  •  ALLBIRDS ZONE  •  QR PICK STATION")

        # Huge LINE & SECTION title
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 27)
        c.drawCentredString(W / 2.0, H - 86, f"LINE {line_num}  •  SEC {sec_num}")

        # Levels pill badge
        c.setLineWidth(1.4)
        c.roundRect(22, H - 116, W - 44, 21, 5, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 8.8)
        c.drawCentredString(W / 2.0, H - 109, "COVERS LEVELS 1 • 2 • 3 • 4   (PASTE ON LEVEL 1)")

        # Crisp vector QR code
        _draw_qr_matrix(c, scan_url, qr_x, qr_y, qr_size)

        # Station ID bar
        c.setFont("Courier-Bold", 11.5)
        c.drawCentredString(W / 2.0, 106, f"STATION: {code}")

        # Divider line
        c.setLineWidth(1.0)
        c.line(22, 96, W - 22, 96)

        # Worker instructions
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(W / 2.0, 83, "STAFF INSTRUCTIONS (WHEN TAKING ANY PIECE):")
        c.setFont("Helvetica", 8.5)
        c.drawString(26, 69, "1. Scan this QR code with your phone camera")
        c.drawString(26, 56, f"2. Enter/Select Style & choose Level (1, 2, 3, or 4) in Sec {sec_num}")
        c.drawString(26, 43, "3. Enter pieces taken & tap SAVE to deduct from inventory")

        # Footer URL + label index
        c.setFont("Helvetica", 6.5)
        c.drawCentredString(W / 2.0, 20, f"{scan_url}   •   Label {idx} of {total}")

        c.showPage()

    c.save()
    pdf_bytes = buf.getvalue()
    _PDF_CACHE[key] = pdf_bytes
    return pdf_bytes
