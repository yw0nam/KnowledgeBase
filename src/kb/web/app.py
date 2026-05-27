"""FastAPI app for the kb-web review console.

Phase A scope: a single read-only endpoint that returns every wiki
page currently in `review_status: pending_for_approve`, with full body
and frontmatter so the frontend can render rail + detail without a
second round-trip. Approve/reject endpoints land in Phase B.
"""

from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory
from kb.web import config
from kb.web.routes import dashboard, decisions, dispatches, kanban, pages, queue

logger = logging.getLogger(__name__)


def _run_migrations(data_dir: os.PathLike[str]) -> None:
    # alembic/env.py resolves the DB URL from KB_DATA_DIR, so set it here to
    # guarantee migrations run against the same dir the app will open.
    os.environ["KB_DATA_DIR"] = str(data_dir)
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    logger.info("alembic upgrade head complete (data_dir=%s)", data_dir)


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
        allow_headers=["Content-Type"],
    )
    app.state.config = cfg
    _run_migrations(cfg.data_dir)
    app.state.engine = make_engine(cfg.data_dir)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.include_router(queue.router, prefix="/api")
    app.include_router(pages.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(kanban.router, prefix="/api")
    app.include_router(dispatches.router, prefix="/api")
    app.include_router(decisions.router, prefix="/api")
    return app


app = create_app()
