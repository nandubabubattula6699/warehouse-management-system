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

# Release 1b-a ships without migration 0003; its tests come back with 1b-b.
needs_0003 = pytest.mark.skip(reason="1b-a: migration 0003 (Part 2 unique slot index) ships in 1b-b")
HEAD = "0002"


def test_models_match_migrated_schema():
    """Like `alembic check`: the models and the migrated database must not drift apart."""
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diffs == []


def test_database_is_at_head():
    current, head = database.schema_revisions()
    assert current == head == HEAD


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
    assert f"{HEAD} (head)" in r.stdout


_DRIFT_INDEXES = {"idx_item_part_line_sec", "ix_inventory_items_brand", "ix_inventory_items_location_code",
                  "ix_inventory_items_placement_type", "ix_inventory_items_warehouse_part"}


def test_0001a_aligns_drifted_database_and_changes_no_row(migr_engine):
    """Staging/production drift (2026-11-26 dump): 5 inventory_items indexes missing and server defaults
    on brand/warehouse_part/placement_type. stamp 0001 -> upgrade head must fix exactly that."""
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
        for name in _DRIFT_INDEXES:
            conn.execute(text(f"DROP INDEX {name}"))
        for col, val in (("brand", "ALLBIRDS"), ("warehouse_part", "PART_1"), ("placement_type", "RACK")):
            conn.execute(text(f"ALTER TABLE inventory_items ALTER COLUMN {col} SET DEFAULT '{val}'"))
        _insert_line_cartons(conn)
        before = conn.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall()
    _alembic("stamp", "0001")
    _alembic("upgrade", "head")
    assert f"{HEAD} (head)" in _alembic("current").stdout
    insp = inspect(migr_engine)
    assert _DRIFT_INDEXES <= {i["name"] for i in insp.get_indexes("inventory_items")}
    defaults = {c["name"]: c["default"] for c in insp.get_columns("inventory_items")}
    assert [defaults[c] for c in ("brand", "warehouse_part", "placement_type")] == [None, None, None]
    with migr_engine.connect() as conn:
        after = conn.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall()
    assert [r[:-1] for r in after] == [tuple(r) for r in before]  # last column = is_active (new in 0002)


def test_compare_schema_ignores_column_order(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from compare_schema import normalize
    a, b = tmp_path / "a.sql", tmp_path / "b.sql"
    a.write_text("CREATE TABLE public.t (\n    id integer NOT NULL,\n    price numeric(10,2),\n    brand text\n);\n")
    b.write_text("CREATE TABLE public.t (\n    id integer NOT NULL,\n    brand text,\n    price numeric(10,2)\n);\n")
    assert normalize(str(a)) == normalize(str(b))
    b.write_text("CREATE TABLE public.t (\n    id integer NOT NULL,\n    brand text DEFAULT 'X',\n"
                 "    price numeric(10,2)\n);\n")
    assert normalize(str(a)) != normalize(str(b))


def _insert_p2(conn, style, qty, active=True, pcs=8, box=None):
    """A Part 2 (Rows) row; is_active only exists from 0002 on."""
    conn.execute(text(
        "INSERT INTO inventory_items (style, color, size, row_pos, section, level, box_num, pcs_per_box, "
        "warehouse_part, brand, location, quantity, is_active) "
        "VALUES (:s, 'CAMO', 'OS', '4', '21', '1', :b, :p, 'PART_2', 'VON DUTCH', 'Row 4 • Sec 21 • Lvl 1', :q, :a)"
    ), {"s": style, "q": qty, "a": active, "p": pcs, "b": box})


def _insert_line_cartons(conn):
    """Allbirds (Part 1, Lines) data as it is today: one row per carton, duplicates included."""
    rows = [("TB1WJBK", "7", "2", "1", "4", None, 20)] * 19 + [
        ("TB1WJBK", "8", "2", "1", "4", "3", 60),
        ("TB1WJBK", "8", "2", "1", "4", "3", 60),
        ("A12501", "9", "5", "12", "2", None, 0),
        ("A12501", "9", "5", "12", "2", "BOX-A", 7),
        ("a12501", "9", "14", "35", "1", "12", 144),
    ]
    for style, size, line, sec, lvl, box, qty in rows:
        conn.execute(text(
            "INSERT INTO inventory_items (style, color, size, line, section, level, box_num, pcs_per_box, "
            "warehouse_part, brand, location, quantity) "
            "VALUES (:s, 'STANDARD', :z, :l, :sec, :lvl, :b, 20, 'PART_1', 'ALLBIRDS', :loc, :q)"
        ), {"s": style, "z": size, "l": line, "sec": sec, "lvl": lvl, "b": box, "q": qty,
            "loc": f"Line {line} • Sec {sec} • Lvl {lvl}"})
    conn.execute(text("INSERT INTO stock_movements (item_id, style, change_amount, quantity_after) "
                      "SELECT id, style, quantity, quantity FROM inventory_items WHERE warehouse_part = 'PART_1'"))


LINE_ROWS = "warehouse_part = 'PART_1' OR coalesce(line, '') <> ''"


def _line_snapshot(eng):
    """Per Line: row count, total pcs, boxes (numeric box # = that many cartons, else 1 carton), plus every
    Line row's full content (all columns that exist since the baseline) and its stock history."""
    with eng.connect() as conn:
        per_line = conn.execute(text(
            f"SELECT line, count(*), sum(quantity), "
            f"sum(CASE WHEN box_num ~ '^[0-9]+$' THEN box_num::int ELSE 1 END) "
            f"FROM inventory_items WHERE {LINE_ROWS} GROUP BY line ORDER BY line"
        )).fetchall()
        rows = conn.execute(text(
            f"SELECT id, style, brand, warehouse_part, placement_type, color, size, line, section, level, row_pos, "
            f"box_num, location_code, location, pcs_per_box, quantity, created_at, updated_at "
            f"FROM inventory_items WHERE {LINE_ROWS} ORDER BY id"
        )).fetchall()
        history = conn.execute(text(
            f"SELECT id, item_id, style, change_amount, quantity_after, movement_type, created_at "
            f"FROM stock_movements WHERE item_id IN (SELECT id FROM inventory_items WHERE {LINE_ROWS}) ORDER BY id"
        )).fetchall()
    return per_line, rows, history


def test_no_line_row_is_changed_by_any_migration(migr_engine):
    """Allbirds (Part 1, Lines) must never be changed by a migration: row count, total pcs and boxes
    per Line - and every Line row and its history - are identical after every upgrade/downgrade,
    including an upgrade that 0003 refuses because Part 2 has duplicates."""
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        _insert_line_cartons(conn)
    before = _line_snapshot(migr_engine)
    per_line = {line: (n, pcs, boxes) for line, n, pcs, boxes in before[0]}
    assert per_line == {"14": (1, 144, 12), "2": (21, 500, 25), "5": (2, 7, 2)}  # sanity: the data is there

    _alembic("upgrade", "head")
    assert _line_snapshot(migr_engine) == before
    with migr_engine.connect() as conn:  # still one row per carton, all active
        assert conn.execute(text(f"SELECT bool_and(is_active) FROM inventory_items WHERE {LINE_ROWS}")).scalar()

    _alembic("downgrade", "0002")
    assert _line_snapshot(migr_engine) == before
    _alembic("downgrade", "0001")
    assert _line_snapshot(migr_engine) == before

    # Part 2 duplicates present: 1b-a's head (0002) still applies, and Lines are still untouched.
    _alembic("upgrade", "0002")
    with migr_engine.begin() as conn:
        _insert_p2(conn, "VDBP-039", 8)
        _insert_p2(conn, "VDBP-039", 8)
    _alembic("upgrade", "head")
    assert _line_snapshot(migr_engine) == before


def test_1b_a_production_path_with_part2_duplicates_changes_no_data(migr_engine):
    """Release 1b-a on a database like production today: un-managed old schema with Part 2 duplicate
    rows -> stamp 0001 -> upgrade head (= 0002). It must apply, change no row, and leave the duplicates
    for the app's Deactivate."""
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))  # looks like production: never stamped
        _insert_line_cartons(conn)
        for qty in (24, 0, 0):  # the VDBP-039 group as it is in production
            conn.execute(text(
                "INSERT INTO inventory_items (style, color, size, row_pos, section, level, pcs_per_box, "
                "warehouse_part, brand, location, quantity) VALUES ('VDBP-039', 'CAMO', 'OS', '4', '21', '1', 8, "
                "'PART_2', 'VON DUTCH', 'Row 4 • Sec 21 • Lvl 1', :q)"), {"q": qty})
        before = conn.execute(text("SELECT id, style, quantity FROM inventory_items ORDER BY id")).fetchall()
        hist_before = conn.execute(text("SELECT count(*) FROM stock_movements")).scalar()
    _alembic("stamp", "0001")
    _alembic("upgrade", "head")
    assert f"{HEAD} (head)" in _alembic("current").stdout
    with migr_engine.connect() as conn:
        assert conn.execute(text("SELECT id, style, quantity FROM inventory_items ORDER BY id")).fetchall() == before
        assert conn.execute(text("SELECT count(*) FROM stock_movements")).scalar() == hist_before
        assert conn.execute(text("SELECT bool_and(is_active) FROM inventory_items")).scalar() is True
    assert ACTIVE_SLOT_INDEX not in {i["name"] for i in inspect(migr_engine).get_indexes("inventory_items")}


@needs_0003
def test_0003_refuses_part2_duplicates_and_changes_nothing(migr_engine):
    _alembic("upgrade", "0002")
    with migr_engine.begin() as conn:
        _insert_line_cartons(conn)              # Part 1 duplicates: allowed, never reported
        _insert_p2(conn, "VDBP-039", 8)
        _insert_p2(conn, "vdbp-039", 8, box="5")  # same slot (case-insensitive; box # not part of it)
        _insert_p2(conn, "VDBP-039", 8, active=False)  # deactivated: never counts
        _insert_p2(conn, "VDBP-039", 12, pcs=12)  # other pack size = other slot
        before = conn.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall()

    r = _alembic("upgrade", "head", ok=False)
    assert r.returncode != 0
    assert "Migration 0003 NOT applied" in r.stderr and "1 Part 2 slot(s)" in r.stderr
    assert "VDBP-039" in r.stderr and "TB1WJBK" not in r.stderr
    assert "0002" in _alembic("current").stdout
    assert ACTIVE_SLOT_INDEX not in {i["name"] for i in inspect(migr_engine).get_indexes("inventory_items")}
    with migr_engine.connect() as conn:
        after = conn.execute(text("SELECT * FROM inventory_items ORDER BY id")).fetchall()
    assert after == before

    # the read-only report lists exactly that Part 2 group (the Line cartons are not reported)
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_PUBLIC_URL", "POSTGRES_URL")}
    env["DATABASE_URL"] = MIGR_DB_URL
    rep = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "report_duplicate_active_rows.py")],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert rep.returncode == 1, rep.stderr
    assert "Part 2: 1 slot(s) with more than one active row, 2 rows involved." in rep.stdout
    assert "TB1WJBK" not in rep.stdout


@needs_0003
def test_failed_upgrade_rolls_back_all_steps(migr_engine):
    """0001 -> head in one go: 0003 fails on Part 2 duplicates, so 0002 must not stay applied either."""
    _alembic("upgrade", "0001")
    with migr_engine.begin() as conn:
        for _ in range(2):
            conn.execute(text("INSERT INTO inventory_items (style, row_pos, section, level, warehouse_part, location, "
                              "quantity) VALUES ('D1', '3', '5', '2', 'PART_2', 'x', 1)"))
    assert _alembic("upgrade", "head", ok=False).returncode != 0
    assert "0001" in _alembic("current").stdout
    assert "is_active" not in {c["name"] for c in inspect(migr_engine).get_columns("inventory_items")}


@needs_0003
def test_0003_applies_when_clean_and_downgrades(migr_engine):
    _alembic("upgrade", "0002")
    with migr_engine.begin() as conn:
        _insert_line_cartons(conn)
        _insert_p2(conn, "A1", 5)
        _insert_p2(conn, "A1", 5, active=False)
        _insert_p2(conn, "A1", 5, pcs=10)
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
