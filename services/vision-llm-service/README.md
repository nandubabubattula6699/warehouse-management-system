# Vision SLM Service (microservice)

Self-hosted photo & label reader microservice for Alexander Warehouse OS.
Uses **RapidOCR (ONNX PP-OCRv4)** + **WarehouseLabelSLM** (a contextual sequence model trained on all 612+ styles, 126+ colors, and 41+ sizes in the warehouse catalog).

## Capabilities
- Reads any uploaded or phone-camera image of a shoe box, carton sticker, or packing label.
- Extracts **Style**, **Color**, **Qty / Pieces**, **Pcs/Box**, **Size**, **Brand**, and **all raw text** line-by-line with confidence scores.
- Automatically repairs common OCR misreads (`0↔O`, `1↔I`, `5↔S`, `8↔B`) against the warehouse catalog and looks up live warehouse rack locations.
- Supports **active learning** (`POST /scan/api/feedback`) and **live retraining** (`POST /scan/api/train`) from PostgreSQL inventory.

## Endpoints (under `/scan`)
- `GET /scan` — Mobile-first Camera & Photo Upload Scanner UI
- `POST /scan/api/analyze` — Extract Style, Color, Qty, Size, and Text from image or raw text
- `GET /scan/api/model-info` — Training dataset & validation accuracy report
- `POST /scan/api/train` — Retrain model on live Postgres catalog + saved corrections (**requires `X-Internal-Key`**)
- `POST /scan/api/feedback` — Save verified correction & retrain (**requires `X-Internal-Key`**)

Train/feedback require `INTERNAL_API_KEY` (same value as the main app). Browsers never hold the key:
the main app's `/scan/*` gateway adds it only for a logged-in Admin or Manager, and strips any
`X-Internal-Key` a client sends.
- `GET /scan/health` — Service health check
