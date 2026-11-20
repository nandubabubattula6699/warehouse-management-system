import os
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

SYSTEM_INSTRUCTION = """
You are an expert Warehouse Management System (WMS) document intake specialist for Alexander Warehouse.
You are given photographs or scanned documents of a Packing List and/or Commercial Invoice for an incoming shipment.
Analyze all tables, line items, carton marks, style codes, colors, sizes, and quantities.
Only report values that are actually present in the documents. Never invent line items.

Extract all details into STRICT JSON matching this format:
{
  "po_number": "PO or Invoice or Container number (or null if not found)",
  "carrier_vendor": "Vendor, Supplier, or Shipper name (or null if not found)",
  "pallets_count": integer (estimated or stated pallets, default 1),
  "total_boxes": integer (sum of all cartons/boxes),
  "total_units": integer (sum of all pieces/units),
  "notes": "Brief summary of shipment contents and condition",
  "items": [
    {
      "style": "Exact Style Code or SKU e.g. A12501, VDSW-2092 SND, VOSB-028",
      "brand": "ALLBIRDS or VON DUTCH or VALENTINO or ED HARDY",
      "color": "Color name or STANDARD",
      "size": "Shoe or apparel size e.g. 8, 9.5, 10, M, L, OS",
      "box_count": integer (number of cartons for this line),
      "pcs_per_box": integer or null (pieces per carton if given),
      "quantity": integer (total pieces received for this line),
      "warehouse_part": "PART_1 for Allbirds styles (A12..., TB..., TR...), PART_2 for Von Dutch/Valentino/Ed Hardy"
    }
  ]
}
Return ONLY valid JSON without markdown fences.
"""

GEMINI_TIMEOUT_SECONDS = 60


class DocumentParserError(Exception):
    """Raised when documents cannot be read. Never replaced by sample data.

    status_code: 400 = bad input, 503 = AI reader not configured, 502 = AI call failed / bad answer.
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _extract_base64_payload(data_uri: str) -> tuple[str, str]:
    """Parse 'data:image/jpeg;base64,...' into (mime_type, base64_data)."""
    if not data_uri:
        return ("image/jpeg", "")
    if "," in data_uri and data_uri.startswith("data:"):
        header, b64 = data_uri.split(",", 1)
        mime = header.split(";")[0].replace("data:", "").strip()
        return (mime, b64.strip())
    return ("image/jpeg", data_uri.strip())


def parse_inbound_documents(
    packing_list_data: Optional[str] = None,
    commercial_invoice_data: Optional[str] = None,
    packing_list_filename: Optional[str] = None,
    commercial_invoice_filename: Optional[str] = None,
    raw_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Read packing list / commercial invoice with Google Gemini.

    Requires env vars GEMINI_API_KEY (or GOOGLE_API_KEY) and GEMINI_MODEL. On any problem this
    raises DocumentParserError — it NEVER returns sample or guessed data.
    """
    if not (packing_list_data or commercial_invoice_data or (raw_text and raw_text.strip())):
        raise DocumentParserError("No document provided. Upload a packing list or commercial invoice.", 400)

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model = (os.getenv("GEMINI_MODEL") or "").strip()
    if not api_key or not model:
        missing = [n for n, v in (("GEMINI_API_KEY", api_key), ("GEMINI_MODEL", model)) if not v]
        raise DocumentParserError(
            "AI document reader is not configured (missing " + ", ".join(missing) + "). "
            "Enter the shipment lines manually.",
            503,
        )

    return _call_gemini_vision(
        api_key=api_key,
        model=model,
        packing_list_data=packing_list_data,
        commercial_invoice_data=commercial_invoice_data,
        raw_text=raw_text,
    )


def _call_gemini_vision(
    api_key: str,
    model: str,
    packing_list_data: Optional[str] = None,
    commercial_invoice_data: Optional[str] = None,
    raw_text: Optional[str] = None
) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._\-]+", model):
        raise DocumentParserError(f"GEMINI_MODEL '{model}' is not a valid model name.", 503)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    parts: List[Dict[str, Any]] = [
        {"text": SYSTEM_INSTRUCTION}
    ]

    if raw_text:
        parts.append({"text": f"Document text contents:\n{raw_text}"})

    for doc in (packing_list_data, commercial_invoice_data):
        if doc:
            mime, b64 = _extract_base64_payload(doc)
            if b64:
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        # API key in a header, not the URL, so it does not end up in proxy/access logs.
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise DocumentParserError(
            f"AI document reader failed (Gemini HTTP {e.code}{': ' + detail[:200] if detail else ''}). "
            "Nothing was extracted — enter the shipment lines manually or try again.",
            502,
        )
    except Exception as e:
        raise DocumentParserError(
            f"AI document reader could not be reached ({type(e).__name__}). "
            "Nothing was extracted — enter the shipment lines manually or try again.",
            502,
        )

    try:
        text_resp = res_data["candidates"][0]["content"]["parts"][0]["text"]
        clean_json = text_resp.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json)
            clean_json = re.sub(r"\s*```$", "", clean_json)
        parsed = json.loads(clean_json)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("items", []), list):
            raise ValueError("unexpected JSON shape")
    except Exception:
        raise DocumentParserError(
            "AI document reader returned an unreadable answer. Nothing was extracted — "
            "enter the shipment lines manually or try again.",
            502,
        )

    if not parsed.get("items"):
        raise DocumentParserError(
            "AI document reader found no line items in the documents. Check the photo/scan "
            "or enter the shipment lines manually.",
            502,
        )

    parsed["ai_model"] = f"Gemini ({model})"
    return parsed
