
"""SQLAlchemy engine/session.
SQLite for development; any SQLAlchemy URL (e.g. PostgreSQL) for production.
"""

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


_settings = get_settings()

database_url = _settings.database_url

# This project currently uses SQLAlchemy's synchronous engine.
# If .env contains sqlite+aiosqlite, convert it to normal SQLite.
if database_url.startswith("sqlite+aiosqlite://"):
    database_url = database_url.replace(
        "sqlite+aiosqlite://",
        "sqlite://",
        1,
    )

_connect_args = (
    {"check_same_thread": False}
    if database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Return a naive UTC timestamp portable across SQLite/PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db() -> Iterator[Session]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

