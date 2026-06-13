"""Session scope context manager for in-process callers.

Provides a single ``session_scope()`` context manager that yields
``(session, data_dir)`` so CLIs and MCP tools don't duplicate engine/session
boilerplate.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import Session

from kb import data_dir
from kb.db import make_engine, make_session_factory

__all__ = ["session_scope"]


@contextlib.contextmanager
def session_scope() -> Generator[tuple[Session, Path], None, None]:
    """Context manager yielding ``(session, data_dir)`` for in-process callers.

    The engine is created fresh on entry (reads ``DATABASE_URL``) and disposed
    on exit.  The session is always closed on exit regardless of exceptions.

    Example::

        with session_scope() as (session, ddir):
            rows = session.execute(select(Page)).scalars().all()
            export_all(session, ddir)
    """
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session, data_dir()
    finally:
        session.close()
        engine.dispose()
