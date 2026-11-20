"""Phase 1a (c)(d)(h): startup never touches inventory, DB URL required, history-protecting deletes."""
import os
import subprocess
import sys

from app.main import seed_if_empty
from app.models import InventoryItem, StockMovement
from tests.conftest import ROOT


def _run_py(code: str, env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "DATABASE_PUBLIC_URL", "POSTGRES_URL")}
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=60)


def test_startup_does_not_seed_empty_inventory(db):
    seed_if_empty()
    assert db.query(InventoryItem).count() == 0


def test_startup_does_not_modify_existing_rows(db):
    # Row deliberately missing location_code/brand (the old backfill trigger) and no Line 14 rows.
    item = InventoryItem(style="A12501", location="custom label", quantity=7, line="3", brand=None,
                         location_code=None)
    db.add(item)
    db.commit()
    seed_if_empty()
    db.expire_all()
    rows = db.query(InventoryItem).all()
    assert len(rows) == 1
    assert rows[0].location == "custom label"
    assert rows[0].location_code is None
    assert rows[0].quantity == 7


def test_app_refuses_to_start_without_database_url():
    # The local .env may define DATABASE_URL, so neutralise load_dotenv() in the child process.
    r = _run_py(
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; import app.database",
        {"PYTHONPATH": ROOT},
    )
    assert r.returncode != 0
    assert "DATABASE_URL is not set" in r.stderr


def test_app_rejects_sqlite_url():
    r = _run_py(
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; import app.database",
        {"PYTHONPATH": ROOT, "DATABASE_URL": "sqlite:///./x.db"},
    )
    assert r.returncode != 0
    assert "PostgreSQL" in r.stderr


def test_migrate_script_requires_confirmation_flag():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "migrate_inventory.py")],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert "--i-understand-this-deletes-all-inventory" in r.stdout


def _item_with_history(db, style="A1"):
    item = InventoryItem(style=style, location="Line 1 • Sec 1", line="1", section="1", quantity=5)
    db.add(item)
    db.flush()
    db.add(StockMovement(item_id=item.id, style=style, change_amount=5, quantity_after=5,
                         movement_type="RECEIVING", reason="test", staff_name="t"))
    db.commit()
    return item


def test_delete_blocked_when_history_exists(manager, db):
    item = _item_with_history(db)
    r = manager.delete(f"/api/items/{item.id}")
    assert r.status_code == 409
    assert "Adj" in r.json()["detail"]
    db.expire_all()
    assert db.get(InventoryItem, item.id) is not None
    assert db.query(StockMovement).filter_by(item_id=item.id).count() == 1


def test_delete_allowed_without_history(manager, db):
    item = InventoryItem(style="B1", location="x", quantity=0)
    db.add(item)
    db.commit()
    assert manager.delete(f"/api/items/{item.id}").status_code == 200


def test_bulk_delete_is_all_or_nothing(manager, db):
    with_hist = _item_with_history(db, "A1")
    plain = InventoryItem(style="B1", location="x", quantity=0)
    db.add(plain)
    db.commit()
    r = manager.post("/api/items/bulk-delete", json={"item_ids": [with_hist.id, plain.id]})
    assert r.status_code == 409
    db.expire_all()
    assert db.query(InventoryItem).count() == 2


def test_sheet_delete_with_history_rolls_back_whole_sheet(manager, db):
    item = _item_with_history(db, "A1")
    r = manager.post("/api/sheet-submit", json={"rows": [
        {"action": "IN", "style": "NEWSTYLE", "line": "2", "section": "1", "level": "1", "quantity": 3},
        {"action": "DELETE", "style": "A1", "line": "1", "section": "1"},
    ]})
    assert r.status_code == 409, r.text
    db.expire_all()
    assert db.get(InventoryItem, item.id) is not None
    assert db.query(InventoryItem).filter_by(style="NEWSTYLE").count() == 0


def test_zeroing_via_adjust_then_still_not_deletable(manager, db):
    item = _item_with_history(db)
    assert manager.post(f"/api/items/{item.id}/adjust", json={"change_amount": -5}).status_code == 200
    assert manager.delete(f"/api/items/{item.id}").status_code == 409
    db.expire_all()
    assert db.get(InventoryItem, item.id).quantity == 0
    assert db.query(StockMovement).filter_by(item_id=item.id).count() == 2
