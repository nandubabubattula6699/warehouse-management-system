"""
Vision SLM Service (microservice)
---------------------------------
Reads warehouse box/carton/label images using RapidOCR (ONNX PP-OCRv4) +
WarehouseLabelSLM (a contextual sequence model trained on Alexander Warehouse's
live catalog of styles, colors, sizes, and quantities).

All routes live under /scan so the service works identically directly or behind the gateway.
"""
import base64
import json
import os
import threading
import time
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import catalog_client
from app.config import FEEDBACK_PATH, MAX_IMAGE_BYTES, MODEL_PATH, REPORT_PATH, STATIC_DIR
from app.ocr_engine import extract_text_from_image, get_ocr_engine
from app.slm_model import WarehouseLabelSLM
from app.trainer import train_warehouse_slm

app = FastAPI(
    title="Warehouse OS - Vision SLM Service",
    version="1.0.0",
    docs_url="/scan/docs",
    openapi_url="/scan/openapi.json",
)

_MODEL_LOCK = threading.RLock()
_SLM: Optional[WarehouseLabelSLM] = None


def _get_model() -> WarehouseLabelSLM:
    global _SLM
    with _MODEL_LOCK:
        if _SLM is None:
            if os.path.exists(MODEL_PATH):
                _SLM = WarehouseLabelSLM.load(MODEL_PATH)
            else:
                train_warehouse_slm()
                _SLM = WarehouseLabelSLM.load(MODEL_PATH)
        return _SLM


def _feedback_count() -> int:
    if not os.path.exists(FEEDBACK_PATH):
        return 0
    with open(FEEDBACK_PATH, encoding="utf-8") as f:
        return sum(1 for ln in f if ln.strip())


@app.on_event("startup")
def warm_up():
    _get_model()
    get_ocr_engine()


# ----------------------------------------------------------------------------- health & pages
@app.get("/scan/health")
async def health():
    slm = _get_model()
    return {
        "status": "ok",
        "service": "vision-llm-service",
        "model_loaded": slm is not None,
        "styles_known": len(slm.vocab.styles),
        "colors_known": len(slm.vocab.colors),
        "feedback_samples": _feedback_count(),
    }


@app.get("/scan", include_in_schema=False)
@app.get("/scan/", include_in_schema=False)
async def scan_ui():
    return FileResponse(os.path.join(STATIC_DIR, "scan.html"))


# ----------------------------------------------------------------------------- model info & training
@app.get("/scan/api/model-info")
async def model_info():
    slm = _get_model()
    report = dict(slm.metadata or {})
    if not report and os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, encoding="utf-8") as f:
            report = json.load(f)
    report["feedback_samples_saved"] = _feedback_count()
    return report


@app.post("/scan/api/train")
async def retrain_model():
    """Retrain the Warehouse Small Language Model on live Postgres catalog + worker feedback."""
    global _SLM
    try:
        report = train_warehouse_slm()
        fresh = WarehouseLabelSLM.load(MODEL_PATH)
        with _MODEL_LOCK:
            _SLM = fresh
        report["feedback_samples_saved"] = _feedback_count()
        return {"status": "ok", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")


class FeedbackPayload(BaseModel):
    raw_text: str
    style: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    quantity: Optional[int] = None
    pcs_per_box: Optional[int] = None
    retrain_now: bool = True


@app.post("/scan/api/feedback")
async def save_feedback(payload: FeedbackPayload):
    """Save verified text-to-field correction so the Small LM learns from real photos."""
    global _SLM
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is required.")
    os.makedirs(os.path.dirname(FEEDBACK_PATH), exist_ok=True)
    record = {
        "raw_text": payload.raw_text,
        "style": payload.style.strip().upper() if payload.style else None,
        "color": payload.color.strip().upper() if payload.color else None,
        "size": payload.size.strip().upper() if payload.size else None,
        "quantity": payload.quantity,
        "pcs_per_box": payload.pcs_per_box,
    }
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    report = None
    if payload.retrain_now:
        report = train_warehouse_slm()
        fresh = WarehouseLabelSLM.load(MODEL_PATH)
        with _MODEL_LOCK:
            _SLM = fresh
    return {
        "status": "ok",
        "feedback_samples_saved": _feedback_count(),
        "retrained": payload.retrain_now,
        "report": report,
    }


# ----------------------------------------------------------------------------- image & text analysis
def _decode_data_uri(data_uri: str) -> bytes:
    raw = data_uri.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


@app.post("/scan/api/analyze")
async def analyze_image_or_text(
    request: Request,
    file: Optional[UploadFile] = File(None),
):
    """
    Analyze a photo/image (multipart upload or JSON base64 `image_data`) OR raw `raw_text`.
    Extracts Style, Color, Qty/Pieces, Pcs/Box, Size, Brand, full OCR text, and live warehouse stock locations.
    """
    t0 = time.time()
    image_bytes: Optional[bytes] = None
    direct_text: Optional[str] = None

    if file is not None:
        image_bytes = await file.read()
    else:
        ctype = (request.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            body = await request.json()
            if body.get("image_data"):
                try:
                    image_bytes = _decode_data_uri(body["image_data"])
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid base64 image_data.")
            elif body.get("raw_text"):
                direct_text = str(body["raw_text"])

    if not image_bytes and not direct_text:
        raise HTTPException(status_code=400, detail="Provide an image file, image_data, or raw_text.")
    if image_bytes and len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 12 MB).")

    if image_bytes:
        try:
            ocr_out = extract_text_from_image(image_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not decode image: {str(e)}")
        raw_text = ocr_out["raw_text"]
    else:
        raw_text = direct_text or ""
        ocr_out = {
            "raw_text": raw_text,
            "lines": [{"text": ln.strip(), "confidence": 1.0} for ln in raw_text.splitlines() if ln.strip()],
            "line_count": len([ln for ln in raw_text.splitlines() if ln.strip()]),
            "avg_ocr_confidence": 1.0,
            "ocr_pass": "direct_text",
        }

    slm = _get_model()
    with _MODEL_LOCK:
        parsed = slm.predict(raw_text)

    locations = []
    if parsed.get("style"):
        locations = await catalog_client.lookup_style_locations(parsed["style"], parsed.get("color"))

    latency_ms = round((time.time() - t0) * 1000.0, 1)
    return JSONResponse({
        "status": "ok",
        "style": parsed["style"],
        "raw_style": parsed["raw_style"],
        "style_confidence": parsed["style_confidence"],
        "color": parsed["color"],
        "raw_color": parsed["raw_color"],
        "color_confidence": parsed["color_confidence"],
        "quantity": parsed["quantity"],
        "quantity_confidence": parsed["quantity_confidence"],
        "pcs_per_box": parsed["pcs_per_box"],
        "size": parsed["size"],
        "brand": parsed["brand"],
        "catalog_verified": parsed["catalog_verified"],
        "raw_text": raw_text,
        "lines": ocr_out["lines"],
        "ocr_pass": ocr_out["ocr_pass"],
        "avg_ocr_confidence": ocr_out["avg_ocr_confidence"],
        "warehouse_locations": locations,
        "tagged_tokens": parsed["tagged_tokens"],
        "model_name": (slm.metadata or {}).get("model_name", "Alexander Warehouse Vision SLM"),
        "latency_ms": latency_ms,
    })
