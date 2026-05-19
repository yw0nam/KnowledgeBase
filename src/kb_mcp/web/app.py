"""FastAPI app for the kb-web review console.

Phase A scope: a single read-only endpoint that returns every wiki
page currently in `review_status: pending_for_approve`, with full body
and frontmatter so the frontend can render rail + detail without a
second round-trip. Approve/reject endpoints land in Phase B.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kb_mcp.web import config
from kb_mcp.web.routes import queue


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
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.config = cfg
    app.include_router(queue.router, prefix="/api")
    return app


app = create_app()
