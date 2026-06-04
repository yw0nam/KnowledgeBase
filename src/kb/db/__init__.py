"""State DB foundation.

Exposes the engine factory, session factory, and FastAPI dependency.
``DATABASE_URL`` wins when set; otherwise the local SQLite fallback is
``data/db/state.db``. SQLite-only PRAGMAs are wired only to SQLite engines.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kb.db.models import (
    Base,
    CronRun,
    Dispatch,
    ExportRecord,
    Handoff,
    MetricsRecord,
    OperationLog,
    Page,
    PageRevision,
    PageSource,
    RawSource,
)

__all__ = [
    "Base",
    "CronRun",
    "Dispatch",
    "ExportRecord",
    "Handoff",
    "MetricsRecord",
    "OperationLog",
    "Page",
    "PageRevision",
    "PageSource",
    "RawSource",
    "db_path",
    "db_url",
    "make_engine",
    "make_session_factory",
    "get_session",
]


def db_path(data_dir: Path) -> Path:
    """Return ``data_dir/db/state.db``, creating the parent dir if needed."""
    db_dir = data_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "state.db"


def db_url(data_dir: Path) -> str:
    """Return the configured SQLAlchemy URL.

    Compose and future hosted deployments set ``DATABASE_URL``. Local
    single-machine operation falls back to SQLite under ``KB_DATA_DIR``.
    """
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured
    return f"sqlite:///{db_path(data_dir)}"


def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.close()


def make_engine(data_dir: Path) -> Engine:
    """Create a SQLAlchemy engine bound to ``DATABASE_URL`` or local SQLite."""
    engine = create_engine(db_url(data_dir), future=True)
    if engine.url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session from ``app.state.session_factory``."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
