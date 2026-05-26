"""Operational state DB foundation.

Exposes the engine factory, session factory, and FastAPI dependency for
``data/db/state.db``. Connection-time PRAGMAs (WAL, foreign_keys,
busy_timeout, synchronous=NORMAL) are registered on the SQLAlchemy
``Engine`` ``connect`` event so every checkout enforces them.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kb.db.models import Base, Dispatch, WikiEdit

__all__ = [
    "Base",
    "Dispatch",
    "WikiEdit",
    "db_path",
    "make_engine",
    "make_session_factory",
    "get_session",
]


def db_path(data_dir: Path) -> Path:
    """Return ``data_dir/db/state.db``, creating the parent dir if needed."""
    db_dir = data_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "state.db"


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


def make_engine(data_dir: Path) -> Engine:
    """Create a SQLAlchemy engine bound to ``data_dir/db/state.db``."""
    url = f"sqlite:///{db_path(data_dir)}"
    return create_engine(url, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session(request) -> Iterator[Session]:
    """FastAPI dependency yielding a session from ``app.state.session_factory``."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
