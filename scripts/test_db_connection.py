import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import engine, init_db, SessionLocal, DATABASE_URL
from app.models import InventoryItem


def test_connection():
    print("=" * 60)
    print("Warehouse OS - Database Connection Diagnostic")
    print("=" * 60)
    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"Target: {safe_url}")
    print("=" * 60)

    try:
        init_db()
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar() if engine.dialect.name == "postgresql" else engine.dialect.name
            print("[SUCCESS] Connected successfully!")
            print(f"[INFO] Server Version: {version}")

        db = SessionLocal()
        try:
            count = db.query(InventoryItem).count()
            print(f"[INFO] Inventory records in database: {count:,}")
        finally:
            db.close()
        return True
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}\n")
        print("TROUBLESHOOTING TIPS:")
        print("1. Confirm PostgreSQL is running.")
        print("2. Check DB_PASSWORD in .env")
        print("3. Verify PostgreSQL is listening on port 5432.")
        return False


if __name__ == "__main__":
    sys.exit(0 if test_connection() else 1)
