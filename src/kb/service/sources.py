"""Service functions for raw source ingestion."""

from __future__ import annotations

__all__ = ["create_raw_source"]

from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb.db.models import RawSource
from kb.service._helpers import _first_heading, commit_and_export
from kb.service._time import now_iso_kst
from kb.service.errors import ServiceError


def create_raw_source(
    session: Session,
    data_dir: Path,
    *,
    source_key: str,
    source_type: str,
    content_md: str,
    frontmatter: dict | None = None,
    source_url: str | None = None,
    title: str | None = None,
    captured_at: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Insert a new RawSource row, export Markdown, and return a result dict.

    Raises:
        ServiceError("conflict", ...)  if ``source_key`` already exists.
        ServiceError("export_failed", ...) if Markdown export fails after DB write.
    """
    row = RawSource(
        source_key=source_key,
        source_type=source_type,
        source_url=source_url,
        title=title or _first_heading(content_md, source_key),
        content_md=content_md,
        frontmatter=frontmatter or {},
        captured_at=captured_at,
        created_at=created_at or now_iso_kst(),
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ServiceError("conflict", "raw_source already exists")
    return commit_and_export(
        session, data_dir, {"id": row.id, "source_key": row.source_key}
    )
