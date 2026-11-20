import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(SERVICE_DIR, "data")
MODELS_DIR = os.path.join(SERVICE_DIR, "models")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

CATALOG_PATH = os.path.join(DATA_DIR, "warehouse_catalog.json")
FEEDBACK_PATH = os.path.join(DATA_DIR, "feedback.jsonl")
MODEL_PATH = os.path.join(MODELS_DIR, "warehouse_slm.pkl")
REPORT_PATH = os.path.join(MODELS_DIR, "training_report.json")

# Inventory service (main Warehouse OS app). Owns live Postgres inventory.
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8000").rstrip("/")
# No default. Without it, live catalog/location lookups are skipped (the bundled catalog is used).
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(12 * 1024 * 1024)))
