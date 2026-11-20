"""Phase 1a (a)(b) + sign-up: login required on every API route, role rules, no default accounts."""
from fastapi.routing import APIRoute

from app.main import app
from app.models import InventoryItem, WarehouseUser
from tests.conftest import PASSWORD, sub_path_params

# Routes that are intentionally reachable without a session.
PUBLIC_API = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),  # returns 401 itself when not logged in
}


def _api_routes():
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield m, r.path


def test_every_non_public_api_route_rejects_anonymous(anon):
    checked = 0
    for method, path in _api_routes():
        if (method, path) in PUBLIC_API:
            continue
        resp = anon.request(method, sub_path_params(path), json={})
        expected = (403, 503) if path.startswith("/api/internal/") else (401,)
        assert resp.status_code in expected, f"{method} {path} -> {resp.status_code} {resp.text[:200]}"
        checked += 1
    assert checked >= 30, "route discovery looks broken"


def test_auth_me_requires_login(anon):
    assert anon.get("/api/auth/me").status_code == 401


def test_staff_can_read_but_not_change_stock(staff, db):
    item = InventoryItem(style="A1", location="Line 1", quantity=5)
    db.add(item)
    db.commit()
    assert staff.get("/api/stats").status_code == 200
    assert staff.get("/api/styles").status_code == 200
    assert staff.post(f"/api/items/{item.id}/adjust", json={"change_amount": -1}).status_code == 403
    assert staff.delete(f"/api/items/{item.id}").status_code == 403
    assert staff.get("/api/export-csv").status_code == 403
    assert staff.post("/api/inbound/shipments/1/approve", json={}).status_code == 403


def test_manager_can_change_stock_but_not_approve(manager, db):
    item = InventoryItem(style="A1", location="Line 1", quantity=5)
    db.add(item)
    db.commit()
    assert manager.post(f"/api/items/{item.id}/adjust", json={"change_amount": -1}).status_code == 200
    assert manager.get("/api/export-csv").status_code == 200
    assert manager.post("/api/inbound/shipments/999/approve", json={}).status_code == 403
    assert manager.get("/api/admin/users").status_code == 403


def test_admin_reaches_approve(admin):
    # 404 (shipment missing) proves the admin passed the access check.
    assert admin.post("/api/inbound/shipments/999/approve", json={}).status_code == 404


def test_signup_ignores_requested_role_and_requires_approval(anon, db):
    r = anon.post("/api/auth/signup", json={
        "full_name": "Eve", "username": "eve", "password": PASSWORD, "role": "ADMIN", "assigned_zone": "BOGUS",
    })
    assert r.status_code == 200, r.text
    u = db.query(WarehouseUser).filter_by(username="eve").one()
    assert u.role == "STAFF"
    assert u.is_approved == 0
    assert u.assigned_zone == "ALL_ZONES"
    login = anon.post("/api/auth/login", json={"username": "eve", "password": PASSWORD})
    assert login.status_code == 403


def test_default_accounts_are_never_created(anon, db):
    anon.post("/api/auth/login", json={"username": "nandu", "password": "x"})
    anon.post("/api/auth/signup", json={"full_name": "A", "username": "someone", "password": PASSWORD})
    names = {u.username for u in db.query(WarehouseUser).all()}
    assert "nandu" not in names
    assert "manager" not in names


def test_adjust_records_logged_in_user_not_payload_name(manager, db):
    from app.models import StockMovement
    item = InventoryItem(style="A1", location="Line 1", quantity=5)
    db.add(item)
    db.commit()
    r = manager.post(f"/api/items/{item.id}/adjust",
                     json={"change_amount": -5, "reason": "Damaged", "staff_name": "Somebody Else"})
    assert r.status_code == 200
    db.expire_all()
    m = db.query(StockMovement).filter_by(item_id=item.id).one()
    assert m.staff_name == "Mgrtest Person"
    assert m.reason == "Damaged"
    assert m.change_amount == -5 and m.quantity_after == 0
    assert m.created_at is not None
