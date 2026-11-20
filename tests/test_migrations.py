"""Phase 1b: Alembic is the only way the schema changes, and the migrations are reversible.

The round-trip tests use a SECOND throw-away database (warehouse_migrations_test) and run
alembic in a subprocess, so they never disturb the main test database.
"""
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app import database
from app.database import Base, engine
from app.inventory_slots import ACTIVE_SLOT_INDEX
from app.main import seed_if_empty
from tests.conftest import ROOT, TEST_DB_URL, _ensure_database_exists

MIGR_DB_URL = urlunsplit(urlsplit(TEST_DB_URL)._replace(path="/warehouse_migrations_test"))
assert urlsplit(MIGR_DB_URL).path.endswith("_test")  # same local *_test safety rule as conftest


def test_models_match_migrated_schema():
    """Like `alembic check`: the models and the migrated database must not drift apart."""
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diffs == []


def test_database_is_at_head():
    current, head = database.schema_revisions()
    assert current == head == "0003"


def test_app_refuses_to_start_on_outdated_schema(monkeypatch):
    monkeypatch.setattr(database, "schema_revisions", lambda: ("0001", "0002"))
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        seed_if_empty()


def test_history_fk_is_restrict_at_database_level(db):
    fks = inspect(engine).get_foreign_keys("stock_movements")
    item_fk = next(fk for fk in fks if fk["referred_table"] == "inventory_items")
    assert item_fk["options"].get("ondelete") == "RESTRICT"


def test_no_create_all_or_alter_in_app_code():
    for rel in ("app/main.py", "app/database.py", "app/location_engine.py", "scripts/create_admin.py",
                "scripts/migrate_inventory.py", "scripts/test_db_connection.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "create_all" not in src, rel
        assert "ALTER TABLE" not in src.upper(), rel


# ---------------------------------------------------------------- round trip on a separate DB

def _alembic(*args, ok=True, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_PUBLIC_URL", "POSTGRES_URL")}
    env["DATABASE_URL"] = MIGR_DB_URL
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    if ok:
        assert r.returncode == 0, r.stderr[-2000:]
    return r


@pytest.fixture
def migr_engine():
    _ensure_database_exists(MIGR_DB_URL)
    eng = create_engine(MIGR_DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1))
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    yield eng
    eng.dispose()


def test_upgrade_downgrade_round_trip_keeps_data(migr_engine):
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        conn.execute(text("INSERT INTO inventory_items (id, style, location, quantity) VALUES (1, 'A1', 'x', 3)"))
        conn.execute(text("INSERT INTO stock_movements (item_id, style, change_amount, quantity_after) "
                          "VALUES (1, 'A1', 3, 3)"))

    _alembic("upgrade", "head")
    with migr_engine.connect() as conn:
        assert conn.execute(text("SELECT is_active FROM inventory_items WHERE id = 1")).scalar() is True
    with pytest.raises(Exception, match="foreign key"):
        with migr_engine.begin() as conn:
            conn.execute(text("DELETE FROM inventory_items WHERE id = 1"))

    _alembic("downgrade", "0001")
    cols = {c["name"] for c in inspect(migr_engine).get_columns("inventory_items")}
    assert "is_active" not in cols
    with migr_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM stock_movements")).scalar() == 1

    _alembic("upgrade", "head")
    with migr_engine.connect() as conn:
        assert conn.execute(text("SELECT quantity FROM inventory_items WHERE id = 1")).scalar() == 3


def test_baseline_refuses_existing_unstamped_tables(migr_engine):
    """An existing pre-Alembic database (like production) must be stamped, never re-created."""
    Base.metadata.create_all(bind=migr_engine)  # simulate the old create_all-built schema
    r = _alembic("upgrade", "head", ok=False)
    assert r.returncode != 0
    assert "alembic stamp 0001" in r.stderr


def test_stamp_then_upgrade_existing_database(migr_engine):
    """The production path: old schema -> stamp 0001 -> upgrade head."""
    _alembic("upgrade", "0001")  # identical to the old create_all schema (checked against warehouse_dev)
    with migr_engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))  # now it looks like an un-managed old database
    _alembic("stamp", "0001")
    _alembic("upgrade", "head")
    r = _alembic("current")
    assert "0003 (head)" in r.stdout


def _insert(conn, style, qty, active=True, box=None):
    conn.execute(text(
        "INSERT INTO inventory_items (style, color, size, line, section, level, box_num, location, quantity, is_active) "
        "VALUES (:s, 'STANDARD', '9', '2', '1', '4', :b, 'Line 2 • Sec 1 • Lvl 4', :q, :a)"
    ), {"s": style, "q": qty, "a": active, "b": box})


def test_0003_refuses_duplicates_and_changes_nothing(migr_engine):
    _alembic("upgrade", "0002")
    with migr_engine.begin() as conn:
        _insert(conn, "TB1WJBK", 20)
        _insert(conn, "tb1wjbk", 20)          # same slot (case-insensitive)
        _insert(conn, "TB1WJBK", 20, active=False)  # deactivated: never counts
        _insert(conn, "TB1WJBK", 20, box="7")  # other box = other slot
        before = conn.execute(text("SELECT id, style, quantity, is_active FROM inventory_items ORDER BY id")).fetchall()

    r = _alembic("upgrade", "head", ok=False)
    assert r.returncode != 0
    assert "Migration 0003 NOT applied" in r.stderr and "1 style/color/size/location slot(s)" in r.stderr
    assert "TB1WJBK" in r.stderr
    assert "0002" in _alembic("current").stdout
    assert ACTIVE_SLOT_INDEX not in {i["name"] for i in inspect(migr_engine).get_indexes("inventory_items")}
    with migr_engine.connect() as conn:
        after = conn.execute(text("SELECT id, style, quantity, is_active FROM inventory_items ORDER BY id")).fetchall()
    assert after == before

    # the read-only report lists exactly that group
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_PUBLIC_URL", "POSTGRES_URL")}
    env["DATABASE_URL"] = MIGR_DB_URL
    rep = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "report_duplicate_active_rows.py")],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert rep.returncode == 1, rep.stderr
    assert "1 slot(s) with more than one active row, 2 rows involved." in rep.stdout


def test_failed_upgrade_rolls_back_all_steps(migr_engine):
    """0001 -> head in one go: 0003 fails on duplicates, so 0002 must not stay applied either."""
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        for _ in range(2):
            conn.execute(text("INSERT INTO inventory_items (style, location, quantity) VALUES ('D1', 'x', 1)"))
    assert _alembic("upgrade", "head", ok=False).returncode != 0
    assert "0001" in _alembic("current").stdout
    assert "is_active" not in {c["name"] for c in inspect(migr_engine).get_columns("inventory_items")}


def test_0003_applies_when_clean_and_downgrades(migr_engine):
    _alembic("upgrade", "0002")
    with migr_engine.begin() as conn:
        _insert(conn, "A1", 5)
        _insert(conn, "A1", 5, active=False)
        _insert(conn, "A1", 5, box="1")
    _alembic("upgrade", "head")
    assert ACTIVE_SLOT_INDEX in {i["name"] for i in inspect(migr_engine).get_indexes("inventory_items")}
    _alembic("downgrade", "0002")
    assert ACTIVE_SLOT_INDEX not in {i["name"] for i in inspect(migr_engine).get_indexes("inventory_items")}


def test_baseline_downgrade_needs_explicit_flag(migr_engine):
    _alembic("upgrade", "0001")
    r = _alembic("downgrade", "base", ok=False)
    assert r.returncode != 0
    assert "Refusing to downgrade below the baseline" in r.stderr
    _alembic("downgrade", "base", extra_env={"ALLOW_BASELINE_DOWNGRADE": "1"})
    assert not inspect(migr_engine).has_table("inventory_items")
