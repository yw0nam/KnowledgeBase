"""Tests for kb.service.session.session_scope."""

from __future__ import annotations

from sqlalchemy import text


def test_session_scope_yields_working_session(database_url: str, data_dir):
    """session_scope should yield a live session that can execute SQL."""
    from kb.service.session import session_scope

    with session_scope() as (session, ddir):
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_session_scope_yields_correct_data_dir(database_url: str, data_dir):
    """ddir from session_scope must equal the KB_DATA_DIR fixture path."""
    from kb.service.session import session_scope

    with session_scope() as (session, ddir):
        assert ddir == data_dir


def test_session_scope_closes_cleanly(database_url: str, data_dir):
    """session_scope must not raise on exit."""
    from kb.service.session import session_scope

    # If the context manager raises, this test will fail
    with session_scope() as (session, ddir):
        session.execute(text("SELECT 1"))
    # reaching here means clean exit
