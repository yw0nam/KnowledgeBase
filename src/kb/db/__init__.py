"""State DB foundation.

Exposes the engine factory and session factory.
Postgres is the sole source of truth; the SQLAlchemy URL comes from
``DATABASE_URL`` and is required (there is no SQLite fallback).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
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
    "db_url",
    "make_engine",
    "make_session_factory",
]


def db_url() -> str:
    """Return the SQLAlchemy URL from ``DATABASE_URL``.

    Postgres is the sole backend. ``DATABASE_URL`` is required; there is no
    SQLite fallback.
    """
    configured = os.environ.get("DATABASE_URL")
    if not configured:
        raise RuntimeError(
            "DATABASE_URL is required (Postgres is the sole source of truth)"
        )
    return configured


def make_engine() -> Engine:
    """Create a SQLAlchemy engine bound to ``DATABASE_URL``."""
    return create_engine(db_url(), future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
