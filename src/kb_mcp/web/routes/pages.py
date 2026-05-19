"""Per-page mutation endpoints.

POST /api/pages/{stem}/approve and /reject thinly wrap the existing
kb_mcp.cli.wiki_review._commands functions so the markdown files
remain the single source of truth and the CLI + API stay in lockstep.

Status semantics follow the workflow spec exactly: only pages in
``pending_for_approve`` can be approved or rejected; the underlying
helpers enforce this and we translate their stderr into HTTP errors.
"""

from __future__ import annotations

import contextlib
import datetime
import io
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from kb_mcp.cli.wiki_review import _commands

router = APIRouter(tags=["pages"])

KST = ZoneInfo("Asia/Seoul")


def _today_kst() -> str:
    return datetime.datetime.now(KST).date().isoformat()


def _now_iso_kst() -> str:
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


class DecisionBody(BaseModel):
    feedback: str = Field(default="", description="Optional reviewer note.")


class DecisionResponse(BaseModel):
    stem: str
    status: str


def _run_capturing_output(fn, *args, **kwargs) -> tuple[int, str, str]:
    """Call a cmd_* helper while capturing its stdout/stderr.

    The helpers print success to stdout and errors via the module's
    _err() (which writes to stderr). Returning the captured text lets
    the route translate failures into proper HTTPException bodies.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout_buf),
        contextlib.redirect_stderr(stderr_buf),
    ):
        rc = fn(*args, **kwargs)
    return rc, stdout_buf.getvalue().strip(), stderr_buf.getvalue().strip()


@router.post("/pages/{stem}/approve", response_model=DecisionResponse)
def approve_page(stem: str, body: DecisionBody, request: Request) -> DecisionResponse:
    cfg = request.app.state.config
    rc, _, err = _run_capturing_output(
        _commands.cmd_approve,
        wiki_dir=cfg.wiki_dir,
        stem=stem,
        feedback=body.feedback,
        today=_today_kst(),
    )
    if rc != 0:
        raise HTTPException(status_code=400, detail=err or "approve failed")
    return DecisionResponse(stem=stem, status="approved")


@router.post("/pages/{stem}/reject", response_model=DecisionResponse)
def reject_page(stem: str, body: DecisionBody, request: Request) -> DecisionResponse:
    cfg = request.app.state.config
    rc, _, err = _run_capturing_output(
        _commands.cmd_reject,
        wiki_dir=cfg.wiki_dir,
        rejected_dir=cfg.rejected_dir,
        data_dir=cfg.data_dir,
        stem=stem,
        feedback=body.feedback,
        today=_today_kst(),
        now_iso=_now_iso_kst(),
        rejected_by="user",
    )
    if rc != 0:
        raise HTTPException(status_code=400, detail=err or "reject failed")
    return DecisionResponse(stem=stem, status="rejected")
