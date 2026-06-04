"""Shared pytest fixtures: Postgres-backed test databases.

Postgres is the sole backend (no SQLite). Tests reuse the compose ``db`` service
on ``localhost:15432``: a migrated template database is built once per session,
and every test clones it (``CREATE DATABASE … TEMPLATE …``) for isolation, then
drops the clone. Override the server with ``KB_TEST_DATABASE_URL``.

Run ``docker compose up -d db`` before the suite.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory

DEFAULT_MAINT_URL = (
    "postgresql+psycopg://knowledgebase:knowledgebase@localhost:15432/knowledgebase"
)
TEMPLATE_DB = "kb_test_template"


def _maint_url() -> str:
    return os.environ.get("KB_TEST_DATABASE_URL", DEFAULT_MAINT_URL)


def _url_for(dbname: str) -> str:
    return f"{_maint_url().rsplit('/', 1)[0]}/{dbname}"


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _maint_engine():
    return create_engine(_maint_url(), isolation_level="AUTOCOMMIT", future=True)


@pytest.fixture(scope="session")
def pg_template() -> str:
    """Build a migrated template database once per test session."""
    try:
        engine = _maint_engine()
        with engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEMPLATE_DB} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {TEMPLATE_DB}"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"Postgres not reachable at {_maint_url()} ({exc}); "
            "run `docker compose up -d db`"
        )

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _url_for(TEMPLATE_DB)
    try:
        command.upgrade(_alembic_cfg(), "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev

    yield TEMPLATE_DB

    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEMPLATE_DB} WITH (FORCE)"))
    engine.dispose()


@pytest.fixture()
def database_url(pg_template: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Clone the template into a throwaway per-test database; set DATABASE_URL."""
    dbname = f"kb_test_{uuid.uuid4().hex}"
    engine = _maint_engine()
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {dbname} TEMPLATE {pg_template}"))
    url = _url_for(dbname)
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    with engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)"))
    engine.dispose()


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Markdown export tree + API token env (no longer the canonical store)."""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(d))
    monkeypatch.setenv("KB_API_TOKEN", "test-token")
    return d


@pytest.fixture()
def session(database_url: str):
    engine = make_engine()
    factory = make_session_factory(engine)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()
