from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WarehouseUser

SESSION_COOKIE_NAME = "wh_session"


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hex_digest = stored_hash.split("$", 1)
        expected = hash_password(password, salt)
        return hmac.compare_digest(expected, stored_hash)
    except Exception:
        return False


def ensure_default_admin(db: Session):
    """Ensure Nandu's default Admin account exists so he always has full access."""
    admin = db.query(WarehouseUser).filter(WarehouseUser.username == "nandu").first()
    if not admin:
        admin = WarehouseUser(
            username="nandu",
            email="nandubabubattula@gmail.com",
            full_name="Nandu (Admin)",
            password_hash=hash_password("Nandu@123"),
            role="ADMIN",
            assigned_zone="ALL_ZONES",
            is_approved=1,
            created_at=datetime.utcnow(),
        )
        db.add(admin)
        db.commit()
        print("[Auth] Seeded default Admin user: username='nandu'", flush=True)

    mgr = db.query(WarehouseUser).filter(WarehouseUser.username == "manager").first()
    if not mgr:
        mgr = WarehouseUser(
            username="manager",
            email="manager@warehouse.com",
            full_name="Warehouse Manager",
            password_hash=hash_password("Manager@123"),
            role="MANAGER",
            assigned_zone="ALL_ZONES",
            is_approved=1,
            created_at=datetime.utcnow(),
        )
        db.add(mgr)
        db.commit()
        print("[Auth] Seeded default Manager user: username='manager'", flush=True)


def get_Request_token(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    return token


def get_optional_user(request: Request, db: Session) -> Optional[WarehouseUser]:
    token = get_Request_token(request)
    if not token:
        return None
    user = db.query(WarehouseUser).filter(WarehouseUser.session_token == token).first()
    if not user or user.is_approved != 1:
        return None
    # Update last_seen_at (throttled to every 20 seconds to avoid unnecessary writes)
    now = datetime.utcnow()
    if not user.last_seen_at or (now - user.last_seen_at).total_seconds() > 20:
        user.last_seen_at = now
        db.commit()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> WarehouseUser:
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user


def require_admin(user: WarehouseUser = Depends(require_user)) -> WarehouseUser:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only Admin (Nandu) can manage user access.")
    return user
