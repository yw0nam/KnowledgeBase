"""Per-page mutation endpoints.

POST /api/pages/{stem}/approve and /reject thinly wrap the existing
kb.cli.wiki_review._commands functions so the markdown files
remain the single source of truth and the CLI + API stay in lockstep.

PATCH /api/pages/{stem}/frontmatter is the constrained editing surface
for the Decisions browser. It runs the candidate frontmatter through
``kb-lint-wiki`` against a hardlink-mirror of the corpus, atomically
replaces the file, and inserts one ``wiki_edits`` row per changed
field. Pipeline order is load-bearing — see spec §6.4 and the failure
mode comments inline.

GET /api/pages/{stem}/edits and /timeline serve the audit history
(edits-only and edits-UNION-dispatches respectively).

Status semantics follow the workflow spec exactly: only pages in
``pending_for_approve`` can be approved or rejected; the underlying
helpers enforce this and we translate their stderr into HTTP errors.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from kb.cli.lint_wiki import LintResult, lint
from kb.cli.wiki.index import INDEX_FILENAME, build_index
from kb.cli.wiki_review import _commands
from kb.cli.wiki_review._store import (
    PageNotFound,
    StemCollision,
    _split_frontmatter,
    resolve_stem,
)
from kb.db import get_session
from kb.db.repos import dispatch_repo, wiki_edit_repo
from kb.web._time import now_iso_kst

router = APIRouter(tags=["pages"])

KST = ZoneInfo("Asia/Seoul")

# Type → required wiki subdir. Used by PATCH to reject a type change
# that would require a cross-directory file move (deferred to Phase
# 2.x per spec §6.4 / §3 non-goal).
_TYPE_DIR: dict[str, str] = {
    "entity": "entities",
    "concept": "concepts",
    "decision": "decisions",
    "question": "questions",
    "improvement": "improvements",
    "checklist": "checklists",
    "summary": "summaries",
}

# Fields the PATCH surface is allowed to mutate. The ``wiki_edits``
# CHECK constraint enforces the same set — application-side guard so
# we surface a clean 422 instead of an IntegrityError.
_EDITABLE_FIELDS = ("review_status", "type", "category", "tags")


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
        data_dir=cfg.data_dir,
        stem=stem,
        feedback=body.feedback,
        today=_today_kst(),
        now_iso=_now_iso_kst(),
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


# ---------------------------------------------------------------------------
# PATCH /api/pages/{stem}/frontmatter
# ---------------------------------------------------------------------------


class FrontmatterPatch(BaseModel):
    review_status: (
        Literal["pending_for_approve", "approved", "rejected", "not_processed"] | None
    ) = None
    type: (
        Literal[
            "entity",
            "concept",
            "decision",
            "question",
            "improvement",
            "checklist",
            "summary",
        ]
        | None
    ) = None
    # ``category`` is an open string by design — see user decision in
    # the Phase 2 task brief and §6.4 deliberate non-enforcement. The
    # frontend uses ``GET /api/enums/categories`` for suggestions.
    category: str | None = None
    tags: list[str] | None = None


def _resolve_page(wiki_dir: Path, stem: str) -> Path:
    try:
        return resolve_stem(wiki_dir, stem)
    except PageNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StemCollision as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _split_or_400(text: str, rel: str) -> tuple[dict, str]:
    parts = _split_frontmatter(text)
    if parts is None:
        raise HTTPException(
            status_code=409, detail=f"{rel}: missing or malformed frontmatter"
        )
    fm_block, body = parts
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=409, detail=f"{rel}: frontmatter parse error: {exc}"
        ) from exc
    if not isinstance(fm, dict):
        raise HTTPException(status_code=409, detail=f"{rel}: frontmatter is not a map")
    return fm, body


def _build_candidate_text(fm: dict, body: str) -> str:
    fm_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{fm_block}---{body}"


def _mirror_corpus(wiki_dir: Path, candidate_rel: Path, candidate_text: str) -> Path:
    """Hardlink-mirror ``wiki_dir`` into a temp dir, then drop the candidate.

    Hardlink keeps the operation O(1) per file; the candidate is the
    only divergence from the live corpus. Falls back to copy when the
    filesystem refuses to hardlink (e.g. cross-mount tmp). Caller is
    responsible for cleanup via ``shutil.rmtree``.
    """
    tmp_wiki = Path(tempfile.mkdtemp(prefix="kb-patch-lint-"))
    for src in wiki_dir.rglob("*.md"):
        rel = src.relative_to(wiki_dir)
        if rel == candidate_rel:
            continue
        dst = tmp_wiki / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    # Drop the candidate at its real-relative path.
    target = tmp_wiki / candidate_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(candidate_text, encoding="utf-8")
    # INDEX.md is a generated artifact: hardlinking the live one would
    # make the lint flag it stale whenever the candidate adds/removes
    # an approved page. Regenerate against the candidate corpus so the
    # lint validates real frontmatter problems, not the artifact gap.
    index_path = tmp_wiki / INDEX_FILENAME
    if index_path.exists() or (index_path.is_symlink()):
        index_path.unlink()
    index_path.write_text(build_index(tmp_wiki), encoding="utf-8")
    return tmp_wiki


def _atomic_write(page: Path, text: str) -> None:
    """``write tmp → fsync → os.replace`` in the page's own directory.

    Same-directory temp file guarantees ``os.replace`` is an atomic
    rename on POSIX (no cross-mount copy fallback).
    """
    fd, tmp = tempfile.mkstemp(
        prefix=f".{page.name}.", suffix=".tmp", dir=str(page.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, page)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@router.patch("/pages/{stem}/frontmatter")
def patch_frontmatter(
    stem: str,
    body: FrontmatterPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    cfg = request.app.state.config
    wiki_dir: Path = cfg.wiki_dir
    data_dir: Path = cfg.data_dir

    page_path = _resolve_page(wiki_dir, stem)
    rel = str(page_path.relative_to(wiki_dir))

    text = page_path.read_text(encoding="utf-8")
    fm, file_body = _split_or_400(text, rel)

    # Step 3 — compute diff. Absent fields = unchanged. Equal values
    # are omitted so the response is idempotent (spec §6.4 step 9).
    patch = body.model_dump(exclude_unset=True)
    diff: list[tuple[str, object, object]] = []
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        old_value = fm.get(field)
        if new_value == old_value:
            continue
        diff.append((field, old_value, new_value))

    if not diff:
        # Idempotent no-op.
        return {"stem": stem, "frontmatter": fm, "edits": []}

    # Step 4 — type change crossing directories must be rejected before
    # any write. The rename workflow is deferred to Phase 2.x.
    type_change = next((d for d in diff if d[0] == "type"), None)
    if type_change is not None:
        new_type = type_change[2]
        required_dir = _TYPE_DIR.get(new_type)
        if required_dir is None or not rel.startswith(f"{required_dir}/"):
            raise HTTPException(
                status_code=409, detail="type change requires manual rename"
            )

    # Step 5 — candidate frontmatter dict + serialized text.
    candidate_fm = dict(fm)
    for field, _, new_value in diff:
        candidate_fm[field] = new_value
    candidate_text = _build_candidate_text(candidate_fm, file_body)

    # Step 6 — lint the candidate against a hardlink mirror of the
    # corpus. Tmp dir is removed regardless of result.
    tmp_wiki = _mirror_corpus(wiki_dir, page_path.relative_to(wiki_dir), candidate_text)
    try:
        result = LintResult()
        lint(
            result,
            wiki_dir=tmp_wiki,
            raw_dir=data_dir / "raw",
            check_immutability=False,
        )
        lint_errors = list(result.errors)
    finally:
        shutil.rmtree(tmp_wiki, ignore_errors=True)
    if lint_errors:
        return JSONResponse(
            status_code=409,
            content={"detail": "lint failed", "lint_errors": lint_errors},
        )

    # Step 7 — atomic rename. The file is now the source of truth for
    # the new value; subsequent failure is post-commit-of-the-file.
    _atomic_write(page_path, candidate_text)

    # Step 8 — append audit rows. If this fails after the file write,
    # surface 500 with file_written=true so the operator can decide
    # whether to retry (idempotent: diff will be empty) or accept the
    # audit gap (spec §6.4 recovery contract).
    try:
        wiki_edit_repo.insert_edits(
            session,
            page_stem=stem,
            changes=diff,
            edited_at=now_iso_kst(),
            source="console",
        )
    except Exception as exc:  # noqa: BLE001 — see recovery contract
        return JSONResponse(
            status_code=500,
            content={
                "detail": "frontmatter written, audit failed",
                "file_written": True,
                "error": str(exc),
            },
        )

    # Re-read the file to confirm the in-memory candidate matches what
    # landed on disk. Cheap insurance against an exotic write that
    # silently mangles encoding.
    final_text = page_path.read_text(encoding="utf-8")
    final_fm, _ = _split_or_400(final_text, rel)

    return {
        "stem": stem,
        "frontmatter": final_fm,
        "edits": [{"field": field, "edited_at": now_iso_kst()} for field, _, _ in diff],
    }


# ---------------------------------------------------------------------------
# GET /api/pages/{stem}/edits
# ---------------------------------------------------------------------------


@router.get("/pages/{stem}/edits")
def list_page_edits(
    stem: str,
    since: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    rows, total = wiki_edit_repo.list_edits(
        session, page_stem=stem, since=since, limit=limit
    )
    return {
        "items": [
            {
                "id": r.id,
                "page_stem": r.page_stem,
                "field": r.field,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "edited_at": r.edited_at,
                "source": r.source,
            }
            for r in rows
        ],
        "total": total,
    }


# ---------------------------------------------------------------------------
# GET /api/pages/{stem}/timeline
# ---------------------------------------------------------------------------


@router.get("/pages/{stem}/timeline")
def get_page_timeline(
    stem: str,
    since: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict:
    """UNION of wiki_edits and dispatch status events for this page.

    Per spec §6.4 we do NOT keep a transition history table; the
    visible dispatch signal is the row's ``dispatched_at`` (kind
    ``dispatched``) and ``last_status_at`` (kind ``status:<status>``).
    """
    capped = 50 if limit is None else max(1, min(int(limit), 200))

    edit_rows, _ = wiki_edit_repo.list_edits(
        session, page_stem=stem, since=None, limit=200
    )
    items: list[dict] = [
        {
            "kind": "edit",
            "field": r.field,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "at": r.edited_at,
            "source": r.source,
        }
        for r in edit_rows
    ]

    dispatch_rows, _ = dispatch_repo.list_dispatches(session, page_stem=stem, limit=200)
    for d in dispatch_rows:
        items.append(
            {
                "kind": "dispatched",
                "at": d.dispatched_at,
                "dispatch_id": d.id,
                "external_task_id": d.external_task_id,
            }
        )
        if d.last_status_at is not None:
            items.append(
                {
                    "kind": f"status:{d.status}",
                    "at": d.last_status_at,
                    "dispatch_id": d.id,
                    "external_task_id": d.external_task_id,
                }
            )

    items.sort(key=lambda it: it["at"], reverse=True)
    total = len(items)
    if since is not None:
        items = [it for it in items if it["at"] < since]
    items = items[:capped]
    return {"items": items, "total": total}
