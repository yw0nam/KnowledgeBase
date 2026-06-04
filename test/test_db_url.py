"""Tests for DB URL resolution (Postgres-only; no SQLite fallback)."""

from __future__ import annotations

import pytest

from kb.db import db_url


def test_db_url_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        db_url()


def test_db_url_returns_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    assert db_url() == "postgresql+psycopg://u:p@h:5432/d"
