"""
Test setup for the main Warehouse OS app.

Tests run against a LOCAL, throw-away PostgreSQL database (default name: warehouse_test).
URL comes from TEST_DATABASE_URL, or is derived from DATABASE_URL in .env by swapping the
database name for "warehouse_test". As a safety net the tests refuse to run unless the host is
localhost and the database name ends in "_test" — they can never touch production.
"""
import os
import re
import sys
from urllib.parse import urlsplit, urlunsplit

import pytest
from dotenv import dotenv_values

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def _resolve_test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        base = os.getenv("DATABASE_URL") or dotenv_values(os.path.join(ROOT, ".env")).get("DATABASE_URL")
        if not base:
            pytest.exit("Set TEST_DATABASE_URL (or DATABASE_URL in .env) to a LOCAL PostgreSQL server.", 2)
        parts = urlsplit(base)
        url = urlunsplit(parts._replace(path="/warehouse_test"))
    parts = urlsplit(url)
    if parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        pytest.exit(f"Refusing to run tests against non-local database host '{parts.hostname}'.", 2)
    if not parts.path.rstrip("/").endswith("_test"):
        pytest.exit("Refusing to run tests: test database name must end with '_test'.", 2)
    return url


TEST_DB_URL = _resolve_test_db_url()

# Environment for the app under test — set BEFORE importing app.* (read at import time).
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.pop("DATABASE_PUBLIC_URL", None)
os.environ.pop("POSTGRES_URL", None)
os.environ["INTERNAL_API_KEY"] = "test-internal-key-0123456789"
os.environ["ALLOWED_ORIGINS"] = "https://allowed.example"
os.environ["PICKING_SERVICE_URL"] = "http://127.0.0.1:9"  # never auto-start child services in tests
os.environ["VISION_SERVICE_URL"] = "http://127.0.0.1:9"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("GEMINI_MODEL", None)


def _ensure_database_exists(url: str) -> None:
    import psycopg2
    from psycopg2 import sql

    parts = urlsplit(url.replace("postgresql+psycopg2://", "postgresql://"))
    dbname = parts.path.lstrip("/")
    admin_url = urlunsplit(parts._replace(path="/postgres"))
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
    finally:
        conn.close()


_ensure_database_exists(TEST_DB_URL)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import WarehouseUser  # noqa: E402

TABLES = ["stock_movements", "inventory_items", "inbound_shipment_items", "inbound_shipments",
          "warehouse_users", "warehouse_locations"]

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def make_user(db, username: str, role: str = "STAFF", approved: int = 1, full_name: str | None = None):
    u = WarehouseUser(
        username=username,
        full_name=full_name or f"{username.title()} Person",
        password_hash=hash_password(PASSWORD),
        role=role,
        assigned_zone="ALL_ZONES",
        is_approved=approved,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def anon():
    # No `with` block: lifespan (startup seeding / child services) is NOT run.
    return TestClient(app)


def _logged_in(db, username, role):
    make_user(db, username, role=role)
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def staff(db):
    return _logged_in(db, "stafftest", "STAFF")


@pytest.fixture
def manager(db):
    return _logged_in(db, "mgrtest", "MANAGER")


@pytest.fixture
def admin(db):
    return _logged_in(db, "admintest", "ADMIN")


def sub_path_params(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)
