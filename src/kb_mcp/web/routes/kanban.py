"""Hermes kanban dispatch endpoints.

Exposes:

- ``GET  /api/kanban/boards`` — list Hermes kanban boards (30s TTL cache).
- ``POST /api/pages/{stem}/send-to-kanban`` — dispatch a
  ``pending_for_approve`` improvement page to a chosen Hermes board.

The route layer translates ``_kanban`` and ``_store`` exceptions into
HTTP status codes per the spec's error taxonomy (§6.5). The rollback
path on a frontmatter-write failure is the single endpoint that may
return a body shape other than ``{detail: ...}`` — see step 6.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kb_mcp.cli.wiki_review import _kanban
from kb_mcp.cli.wiki_review._store import (
    PageNotFound,
    StemCollision,
    _split_frontmatter,
    resolve_stem,
)

router = APIRouter(tags=["kanban"])

KST = ZoneInfo("Asia/Seoul")

# Module-level 30s TTL cache for the boards listing. A single key keeps
# this simple — there is only one Hermes per host. Set by the GET
# endpoint, invalidated on a successful POST dispatch.
_BOARDS_CACHE: dict[str, tuple[float, list[dict]]] = {}
_BOARDS_TTL = 30.0


def _now_iso_kst() -> str:
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


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
            status_code=503,
            detail="Hermes kanban is not reachable. Is the daemon running?",
        )
    except _kanban.HermesRejected as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"boards": boards}


def _read_body(path: Path) -> str:
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return text
    return parts[1].lstrip("\n")


def _extract_title(path: Path, body: str) -> str:
    """Return the first H1 if present, else the page stem.

    Matches the spec's intent in §6.4: cards are titled by the page's
    own H1. Falling back to the stem keeps malformed pages dispatchable.
    """
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
    """Render the card body per §6.4, with the metadata fallback.

    The trailing ``<!-- kb-meta: {...} -->`` line replaces the
    unsupported ``--metadata`` flag (see _kanban module docstring).
    """
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
def send_page_to_kanban(stem: str, body: SendToKanbanRequest, request: Request):
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
    import yaml

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
            status_code=503,
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
            status_code=503,
            detail="Hermes kanban is not reachable. Is the daemon running?",
        )
    except _kanban.HermesRejected as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Step 6: write frontmatter; on failure, attempt rollback.
    dispatched_at = _now_iso_kst()
    dispatch_entry = {
        "task_id": card.task_id,
        "board": body.board_slug,
        "dispatched_at": dispatched_at,
        "direction": body.direction_note if body.direction_note else None,
    }
    try:
        _kanban.append_dispatch(page_path, dispatch_entry)
    except Exception:
        try:
            _kanban.archive_card(card.task_id)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": (
                        f"Card exists on board {body.board_slug} but the page "
                        f"frontmatter could not be updated. Archive it manually: "
                        f"hermes kanban archive {card.task_id}"
                    ),
                    "orphan_task_id": card.task_id,
                },
            )
        raise HTTPException(
            status_code=500,
            detail="frontmatter write failed, kanban card rolled back",
        )

    # Step 7: invalidate cache.
    _invalidate_boards_cache()

    # Step 8: success.
    return {
        "task_id": card.task_id,
        "board_slug": body.board_slug,
        "dispatched_at": dispatched_at,
    }
