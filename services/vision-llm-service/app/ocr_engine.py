"""
Vision OCR Engine (RapidOCR ONNX PP-OCRv4)
------------------------------------------
Reads all printed text from box labels, carton stickers, and shipping tags.
Handles phone camera EXIF rotation, resizing, contrast enhancement, and
automatic 90/270-degree orientation recovery if the photo was taken sideways.
"""
import io
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
from rapidocr_onnxruntime import RapidOCR

_OCR_LOCK = threading.Lock()
_OCR_INSTANCE: Optional[RapidOCR] = None


def get_ocr_engine() -> RapidOCR:
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        with _OCR_LOCK:
            if _OCR_INSTANCE is None:
                _OCR_INSTANCE = RapidOCR()
    return _OCR_INSTANCE


def _prepare_rgb_image(image_bytes: bytes, max_side: int = 1600, min_side: int = 560) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    elif longest < min_side and longest > 0:
        scale = min(2.5, min_side / float(longest))
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return np.array(img)


def _enhance_contrast(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    return cv2.cvtColor(eq, cv2.COLOR_GRAY2RGB)


def _run_rapidocr(rgb: np.ndarray) -> List[Dict[str, Any]]:
    ocr = get_ocr_engine()
    with _OCR_LOCK:
        result, _ = ocr(rgb)
    if not result:
        return []
    items = []
    for box, text, score in result:
        clean = (text or "").strip()
        if not clean:
            continue
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        items.append({
            "text": clean,
            "confidence": round(float(score), 4),
            "y_center": (min(ys) + max(ys)) / 2.0,
            "x_left": min(xs),
            "height": max(1.0, max(ys) - min(ys)),
        })
    return items


def _group_into_reading_lines(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort OCR boxes into top-to-bottom reading lines, merging boxes on the same visual row."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: (b["y_center"], b["x_left"]))
    rows: List[List[Dict[str, Any]]] = []
    for item in ordered:
        placed = False
        for row in rows:
            ref_y = sum(r["y_center"] for r in row) / len(row)
            ref_h = sum(r["height"] for r in row) / len(row)
            if abs(item["y_center"] - ref_y) <= max(10.0, ref_h * 0.55):
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    lines = []
    for row in rows:
        row_sorted = sorted(row, key=lambda r: r["x_left"])
        joined_text = " ".join(r["text"] for r in row_sorted).strip()
        avg_conf = sum(r["confidence"] for r in row_sorted) / len(row_sorted)
        lines.append({
            "text": joined_text,
            "confidence": round(avg_conf, 4),
        })
    return lines


def _score_ocr_quality(boxes: List[Dict[str, Any]]) -> Tuple[int, float]:
    if not boxes:
        return (0, 0.0)
    total_chars = sum(len(b["text"]) for b in boxes)
    avg_conf = sum(b["confidence"] for b in boxes) / len(boxes)
    return (total_chars, avg_conf)


def extract_text_from_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Run multi-pass Vision OCR on an image and return reading-order lines + raw text.
    """
    rgb = _prepare_rgb_image(image_bytes)
    best_boxes = _run_rapidocr(rgb)
    best_chars, best_conf = _score_ocr_quality(best_boxes)
    pass_used = "standard"

    # Fallback 1: contrast-enhanced pass if image was dim/washed out or few chars extracted
    if best_chars < 14 or best_conf < 0.72:
        enhanced = _enhance_contrast(rgb)
        cand = _run_rapidocr(enhanced)
        c_chars, c_conf = _score_ocr_quality(cand)
        if (c_chars > best_chars + 3) or (c_chars >= best_chars and c_conf > best_conf + 0.05):
            best_boxes, best_chars, best_conf = cand, c_chars, c_conf
            pass_used = "contrast_enhanced"

    # Fallback 2: check 90° / 270° rotated passes if text is still sparse (sideways phone snap)
    if best_chars < 12 or len(best_boxes) < 2:
        for angle_name, rot_code in [("rotated_90", cv2.ROTATE_90_CLOCKWISE), ("rotated_270", cv2.ROTATE_90_COUNTERCLOCKWISE)]:
            rot_img = cv2.rotate(rgb, rot_code)
            cand = _run_rapidocr(rot_img)
            c_chars, c_conf = _score_ocr_quality(cand)
            if c_chars > best_chars + 4 and c_conf >= 0.65:
                best_boxes, best_chars, best_conf = cand, c_chars, c_conf
                pass_used = angle_name

    lines = _group_into_reading_lines(best_boxes)
    raw_text = "\n".join(ln["text"] for ln in lines)
    return {
        "raw_text": raw_text,
        "lines": lines,
        "line_count": len(lines),
        "avg_ocr_confidence": round(best_conf, 4),
        "ocr_pass": pass_used,
    }
