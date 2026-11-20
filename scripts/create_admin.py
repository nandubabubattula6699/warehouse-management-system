"""
Create (or reset the password of) an ADMIN user. Run manually; the app never creates users by itself.

    python scripts/create_admin.py <username> "<Full Name>" [email]

The password is read from the ADMIN_PASSWORD environment variable if set, otherwise prompted
(hidden input). Nothing is hard-coded.
"""
import getpass
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import func  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.models import WarehouseUser  # noqa: E402

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    username = sys.argv[1].strip().lower()
    full_name = sys.argv[2].strip()
    email = sys.argv[3].strip().lower() if len(sys.argv) > 3 and sys.argv[3].strip() else None

    password = os.getenv("ADMIN_PASSWORD") or getpass.getpass("New admin password: ")
    if not os.getenv("ADMIN_PASSWORD") and password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        return 1

    init_db()
    db = SessionLocal()
    try:
        user = db.query(WarehouseUser).filter(func.lower(WarehouseUser.username) == username).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = "ADMIN"
            user.is_approved = 1
            user.session_token = None
            action = "updated (password reset, sessions cleared)"
        else:
            db.add(WarehouseUser(
                username=username,
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role="ADMIN",
                assigned_zone="ALL_ZONES",
                is_approved=1,
                created_at=datetime.utcnow(),
            ))
            action = "created"
        db.commit()
        print(f"Admin user '{username}' {action}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
