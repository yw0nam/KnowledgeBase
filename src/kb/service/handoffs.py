"""Service functions for Handoff operations.

Extracted from ``kb.web.routes.db_canonical`` route handler with HTTP
specifics removed. HTTP exceptions become ``ServiceError``; ``data_dir``
replaces ``request.app.state.config.data_dir``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb.db.models import Handoff
from kb.lint.handoff import validate_handoff_create
from kb.service._helpers import commit_and_export
from kb.service._time import now_iso_kst
from kb.service.errors import ServiceError


def create_handoff(
    session: Session,
    data_dir: Path,
    *,
    handoff_id: str,
    task_slug: str,
    role: str,
    handoff_seq: int,
    status: str,
    frontmatter: dict,
    body_md: str,
    export_path: str,
    subject: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict:
    """Insert a new Handoff row; run lint before writing.

    Order mirrors the route handler's intent:
    1. Validate with lint — raise ``ServiceError("lint_failed", ...)`` if not ok.
    2. Build the row.
    3. ``session.add``; ``flush`` — raise ``ServiceError("conflict", ...)`` on
       IntegrityError.
    4. ``commit_and_export`` and return its result.
    """
    lint_result = validate_handoff_create(frontmatter, body_md)
    if not lint_result.ok:
        raise ServiceError(
            "lint_failed",
            {"errors": lint_result.errors, "warnings": lint_result.warnings},
        )
    now = now_iso_kst()
    row = Handoff(
        handoff_id=handoff_id,
        task_slug=task_slug,
        subject=subject,
        role=role,
        handoff_seq=handoff_seq,
        status=status,
        frontmatter=frontmatter,
        body_md=body_md,
        export_path=export_path,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ServiceError("conflict", "handoff already exists")
    return commit_and_export(session, data_dir, {"id": row.id})
