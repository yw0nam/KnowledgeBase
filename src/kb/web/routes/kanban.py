"""Hermes kanban dispatch endpoints.

Exposes:

- ``GET  /api/kanban/boards`` — list Hermes kanban boards (30s TTL cache).
- ``POST /api/pages/{stem}/send-to-kanban`` — dispatch a
  ``pending_for_approve`` improvement page to a chosen Hermes board.

Phase 2 (§6.2): dispatch records live in the ``dispatches`` SQL table,
not in page frontmatter. The route creates the Hermes card first, then
inserts the dispatch row. A DB insert failure after a successful card
creation does NOT roll back the card — the route returns 500 with the
orphan ``external_task_id`` so the operator can reclaim it manually.
The Phase 1 rollback path is intentionally gone (spec §6.2).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb.cli.wiki_review import _kanban
from kb.cli.wiki_review._store import (
    PageNotFound,
    StemCollision,
    _split_frontmatter,
    resolve_stem,
)
from kb.db import get_session
from kb.db.repos import dispatch_repo
from kb.web._time import now_iso_kst

router = APIRouter(tags=["kanban"])

# Module-level 30s TTL cache for the boards listing. A single key keeps
# this simple — there is only one Hermes per host. Set by the GET
# endpoint, invalidated on a successful POST dispatch.
_BOARDS_CACHE: dict[str, tuple[float, list[dict]]] = {}
_BOARDS_TTL = 30.0


def _board_to_dict(board: _kanban.Board) -> dict:
    return {"slug": board.slug, "name": board.name, "counts": board.counts}


def _fetch_boards_cached() -> list[dict]:
    cached = _BOARDS_CACHE.get("boards")
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < _BOARDS_TTL:
        return cached[1]
    boards = [_board_to_dict(b) for b in _kanban.list_boards()]
    _BOARDS_CACHE["boards"] = (now, boards)
    return boards


def _invalidate_boards_cache() -> None:
    _BOARDS_CACHE.pop("boards", None)


class SendToKanbanRequest(BaseModel):
    board_slug: str = Field(min_length=1)
    direction_note: str | None = None


@router.get("/kanban/boards")
def get_kanban_boards() -> dict:
    try:
        boards = _fetch_boards_cached()
    except _kanban.HermesUnavailable:
        raise HTTPException(
            status_code=502,
            detail="Hermes kanban is not reachable. Is the daemon running?",
        )
    except _kanban.HermesRejected as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"boards": boards}


def _extract_title(path: Path, body: str) -> str:
    """Return the first H1 if present, else the page stem."""
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or path.stem
    return path.stem


def _compose_card_body(
    title: str,
    rel_path: Path,
    direction_note: str | None,
    page_body: str,
    metadata: dict,
) -> str:
    """Render the card body per §6.4, with the metadata fallback."""
    direction = (
        direction_note
        if (direction_note and direction_note.strip())
        else "(none provided)"
    )
    meta_line = f"<!-- kb-meta: {json.dumps(metadata, separators=(',', ':'))} -->"
    return (
        f"# {title}\n\n"
        "Dispatched from KB review console.\n\n"
        f"Source page: {rel_path}\n\n"
        "## Direction\n"
        f"{direction}\n\n"
        "## Page contents\n"
        f"{page_body}\n\n"
        f"{meta_line}\n"
    )


@router.post("/pages/{stem}/send-to-kanban")
def send_page_to_kanban(
    stem: str,
    body: SendToKanbanRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    cfg = request.app.state.config
    wiki_dir: Path = cfg.wiki_dir

    # Step 1: resolve the page.
    try:
        page_path = resolve_stem(wiki_dir, stem)
    except PageNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StemCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Step 2: gate on review_status.
    text = page_path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise HTTPException(
            status_code=409,
            detail=f"page {stem!r} has no parseable frontmatter",
        )
    try:
        fm = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"page {stem!r} has malformed frontmatter: {exc}",
        )
    if not isinstance(fm, dict) or fm.get("review_status") != "pending_for_approve":
        raise HTTPException(
            status_code=409,
            detail=(
                f"page {stem!r} is not in review_status pending_for_approve "
                "(dispatch is gated to pending pages in Phase 1)"
            ),
        )

    # Step 3: confirm board exists.
    try:
        boards = _fetch_boards_cached()
    except _kanban.HermesUnavailable:
        raise HTTPException(
            status_code=502,
            detail="Hermes kanban is not reachable. Is the daemon running?",
        )
    except _kanban.HermesRejected as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not any(b["slug"] == body.board_slug for b in boards):
        raise HTTPException(
            status_code=400,
            detail=f"board_slug {body.board_slug!r} not found",
        )

    # Step 4: compose card body.
    page_body = parts[1].lstrip("\n")
    rel_path = page_path.relative_to(cfg.data_dir)
    title = _extract_title(page_path, page_body)
    metadata = {"kb_page_stem": stem, "kb_source": "review-console"}
    card_body = _compose_card_body(
        title=title,
        rel_path=rel_path,
        direction_note=body.direction_note,
        page_body=page_body,
        metadata=metadata,
    )

    # Step 5: create the card.
    try:
        card = _kanban.create_card(
            board_slug=body.board_slug, title=title, body=card_body
        )
    except _kanban.HermesUnavailable:
        raise HTTPException(
            status_code=502,
            detail="Hermes kanban is not reachable. Is the daemon running?",
        )
    except _kanban.HermesRejected as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Step 6: persist the dispatch row. No frontmatter write. The only
    # realistic non-success path is a UNIQUE collision on
    # (external_board_id, external_task_id), which surfaces here as
    # IntegrityError; on that path the card is orphaned and we report
    # its id so the operator can `hermes kanban archive` it manually.
    # Anything else (programming bug, DB outage) bubbles to FastAPI's
    # default 500 handler with the real traceback — deliberately not
    # swallowed.
    dispatched_at = now_iso_kst()
    try:
        row = dispatch_repo.create_dispatch(
            session,
            page_stem=stem,
            page_path_at_dispatch=str(rel_path),
            external_board_id=body.board_slug,
            external_task_id=card.task_id,
            direction=body.direction_note if body.direction_note else None,
            idempotency_key=idempotency_key,
            created_at=dispatched_at,
            dispatched_at=dispatched_at,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "DB insert failed after card creation",
                "external_task_id": card.task_id,
            },
        )

    # Step 7: invalidate boards cache so a subsequent GET reflects the
    # new card count.
    _invalidate_boards_cache()

    # Step 8: success — new §6.2 response shape.
    return {
        "id": row.id,
        "external_task_id": row.external_task_id,
        "external_board_id": row.external_board_id,
        "dispatched_at": row.dispatched_at,
    }
