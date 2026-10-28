import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from app.database import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, engine, ensure_database_exists, init_db
from sqlalchemy import text

def test_connection():
    print("=" * 60)
    print("Warehouse OS - PostgreSQL Connection Diagnostic")
    print("=" * 60)
    print(f"Host:     {DB_HOST}")
    print(f"Port:     {DB_PORT}")
    print(f"Database: {DB_NAME}")
    print(f"User:     {DB_USER}")
    print("=" * 60)

    try:
        ensure_database_exists()
        init_db()

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar()
            print(f"[SUCCESS] Connected to PostgreSQL successfully!")
            print(f"[INFO] Server Version: {version}\n")

            from app.models import Product
            from app.database import SessionLocal
            db = SessionLocal()
            count = db.query(Product).count()
            print(f"[INFO] Current products in database: {count}")
            db.close()
            return True
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}\n")
        print("TROUBLESHOOTING TIPS:")
        print("1. Confirm pgAdmin 4 / PostgreSQL is running.")
        print("2. Check your password in .env (DB_PASSWORD=...)")
        print("3. Verify PostgreSQL is listening on port 5432.")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
