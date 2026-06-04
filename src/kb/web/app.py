"""FastAPI app for the kb-web DB-canonical API.

DB-canonical write surface with Bearer auth, plus Markdown export.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kb import REPO_ROOT
from kb.db import db_url, make_engine, make_session_factory
from kb.web import config
from kb.web.routes import db_canonical

logger = logging.getLogger(__name__)


def _run_migrations(data_dir: os.PathLike[str]) -> None:
    # alembic/env.py resolves DATABASE_URL first, then falls back to KB_DATA_DIR,
    # so set KB_DATA_DIR here to keep the SQLite fallback aligned with the app.
    os.environ["KB_DATA_DIR"] = str(data_dir)
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    logger.info("alembic upgrade head complete (db_url=%s)", db_url(Path(data_dir)))


def create_app() -> FastAPI:
    cfg = config.load()
    app = FastAPI(
        title="kb-web",
        description="Local review console for KnowledgeBase wiki pages.",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.state.config = cfg
    _run_migrations(cfg.data_dir)
    app.state.engine = make_engine(cfg.data_dir)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.include_router(db_canonical.router, prefix="/api")
    return app


app = create_app()
