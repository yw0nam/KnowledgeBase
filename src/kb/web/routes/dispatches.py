"""Dispatch ledger endpoints (Phase 2 §6.3).

Three routes:

- ``GET  /api/dispatches`` — paginated listing.
- ``POST /api/dispatches/{id}/status`` — Bearer-protected status push.
- ``POST /api/dispatches/{id}/cancel`` — localhost-only two-state
  cancel; ``?force=true`` bypasses Hermes and force-flips the row.

Bearer auth lives ONLY on the status route per spec §6.5 — every
other write surface is localhost-only.
"""

from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from kb.cli.wiki_review import _kanban
from kb.db import get_session
from kb.db.models import Dispatch
from kb.db.repos import dispatch_repo
from kb.web._time import now_iso_kst

router = APIRouter(tags=["dispatches"])


def _row_payload(row: Dispatch) -> dict:
    return {
        "id": row.id,
        "page_stem": row.page_stem,
        "page_path_at_dispatch": row.page_path_at_dispatch,
        "external_board_id": row.external_board_id,
        "external_task_id": row.external_task_id,
        "direction": row.direction,
        "status": row.status,
        "idempotency_key": row.idempotency_key,
        "created_at": row.created_at,
        "dispatched_at": row.dispatched_at,
        "last_status_at": row.last_status_at,
        "result_payload": row.result_payload,
    }


# ---------------------------------------------------------------------------
# GET /api/dispatches
# ---------------------------------------------------------------------------


@router.get("/dispatches")
def list_dispatches(
    page_stem: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    rows, total = dispatch_repo.list_dispatches(
        session,
        page_stem=page_stem,
        status=status,
        since=since,
        limit=limit,
    )
    return {"items": [_row_payload(r) for r in rows], "total": total}


# ---------------------------------------------------------------------------
# POST /api/dispatches/{id}/status   [Bearer]
# ---------------------------------------------------------------------------


class StatusPushBody(BaseModel):
    status: Literal["in_progress", "done", "failed", "cancelled"]
    result_payload: dict | None = None
    occurred_at: str | None = None


@router.post("/dispatches/{dispatch_id}/status")
def post_status(
    dispatch_id: int,
    body: StatusPushBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    expected = os.environ.get("KB_API_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="KB_API_TOKEN env var not set; status push disabled",
        )
    # Header parsing: require the canonical "Bearer <token>" shape and
    # trim any extra whitespace before the constant-time comparison.
    # compare_digest demands equal-length operands; an empty `provided`
    # short-circuits to 401 before we hit it.
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid bearer token")
    provided = header[len("Bearer ") :].strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid bearer token")

    try:
        row = dispatch_repo.update_status(
            session,
            dispatch_id=dispatch_id,
            new_status=body.status,
            occurred_at=body.occurred_at,
            result_payload=body.result_payload,
            server_now=now_iso_kst(),
        )
    except dispatch_repo.DispatchNotFound:
        raise HTTPException(status_code=404, detail="dispatch not found")
    except dispatch_repo.StatusOutOfOrder:
        raise HTTPException(status_code=409, detail="status_out_of_order")
    except dispatch_repo.TransitionViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _row_payload(row)


# ---------------------------------------------------------------------------
# POST /api/dispatches/{id}/cancel   [localhost]
# ---------------------------------------------------------------------------


@router.post("/dispatches/{dispatch_id}/cancel")
def post_cancel(
    dispatch_id: int,
    force: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    if force:
        try:
            row = dispatch_repo.force_cancel(
                session,
                dispatch_id=dispatch_id,
                server_now=now_iso_kst(),
            )
        except dispatch_repo.DispatchNotFound:
            raise HTTPException(status_code=404, detail="dispatch not found")
        except dispatch_repo.TransitionViolation as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return _row_payload(row)

    # Phase one: flip the row to cancelling.
    try:
        row = dispatch_repo.cancel_phase_one(
            session,
            dispatch_id=dispatch_id,
            server_now=now_iso_kst(),
        )
    except dispatch_repo.DispatchNotFound:
        raise HTTPException(status_code=404, detail="dispatch not found")
    except dispatch_repo.TransitionViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Phase two gate: ask Hermes to archive. On any Hermes failure the
    # row stays in cancelling and we surface 502 so the operator can
    # retry or escape with ?force=true.
    try:
        _kanban.archive_card(row.external_task_id)
    except (_kanban.HermesUnavailable, _kanban.HermesRejected) as exc:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "hermes archive failed",
                "db_state": "cancelling",
                "external_error": str(exc),
            },
        )

    final = dispatch_repo.cancel_phase_two(
        session,
        dispatch_id=dispatch_id,
        server_now=now_iso_kst(),
    )
    return _row_payload(final)
