import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

raw_db_url = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_PUBLIC_URL")
    or os.getenv("POSTGRES_URL")
)

if not raw_db_url:
    # Refuse to start: never fall back to SQLite or a built-in default database/password.
    raise RuntimeError(
        "DATABASE_URL is not set. Set DATABASE_URL to the PostgreSQL connection URL "
        "(e.g. postgresql://user:password@host:5432/warehouse_db) in the environment or .env file."
    )

if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+psycopg2://"):
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if not raw_db_url.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL must be a PostgreSQL URL (postgresql://...). SQLite is not supported.")

DATABASE_URL = raw_db_url

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")


def schema_revisions():
    """(revision the database is at, latest revision in migrations/). The app never changes the schema:
    `alembic upgrade head` does (Railway preDeployCommand / by hand)."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(ALEMBIC_INI)).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def require_current_schema():
    """Refuse to run against a database whose schema is not at the latest migration."""
    current, head = schema_revisions()
    if current != head:
        raise RuntimeError(
            f"Database schema is at revision {current or 'NONE (not managed by Alembic)'}, "
            f"the code needs {head}. Run 'alembic upgrade head' first "
            "(an existing pre-Alembic database must be checked and stamped: see docs/DEPLOY_1B.md)."
        )
    return current
