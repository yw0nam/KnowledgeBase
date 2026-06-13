"""Tests for kb.service.handoffs — RED→GREEN TDD."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from kb.db.models import Handoff
from kb.service.errors import ServiceError

# --------------------------------------------------------------------------- #
# Shared fixtures                                                               #
# --------------------------------------------------------------------------- #

VALID_FRONTMATTER = {
    "handoff_id": "migrate-db:null:opencode:01",
    "task_slug": "migrate-db",
    "subject": None,
    "role": "opencode",
    "handoff_seq": 1,
    "status": "ready",
    "security": {"contains_secrets": False, "redaction_status": "none"},
    "promotion": None,
}

VALID_BODY = (
    "\n# Handoff\n\n"
    "## 1. Assignment\n\n"
    "## 2. Context received\n\n"
    "## 3. Work performed\n\n"
    "## 4. Tool trace\n\n"
    "## 5. Findings / decisions\n\n"
    "## 6. Outputs\n\n"
    "## 7. Verification\n\n"
    "## 8. Risks / uncertainties\n\n"
    "## 9. Next handoff instructions\n\n"
    "## 10. Promotion candidates\n\nDone.\n"
)

EXPORT_PATH = "handoffs/2026/06/migrate-db/opencode_handoff_01.md"


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #


def test_create_handoff_success(data_dir: Path, session) -> None:
    """create_handoff returns export success dict and writes a Markdown file."""
    from kb.service.handoffs import create_handoff

    result = create_handoff(
        session,
        data_dir,
        handoff_id="migrate-db:null:opencode:01",
        task_slug="migrate-db",
        role="opencode",
        handoff_seq=1,
        status="ready",
        frontmatter=VALID_FRONTMATTER,
        body_md=VALID_BODY,
        export_path=EXPORT_PATH,
        subject=None,
    )

    assert result["export"]["status"] == "success"
    assert "id" in result

    # On-disk export
    exported = data_dir / EXPORT_PATH
    assert exported.exists()

    # DB row
    row = session.execute(
        select(Handoff).where(Handoff.handoff_id == "migrate-db:null:opencode:01")
    ).scalar_one()
    assert row.handoff_id == "migrate-db:null:opencode:01"
    assert row.task_slug == "migrate-db"
    assert row.role == "opencode"


def test_create_handoff_conflict(data_dir: Path, session) -> None:
    """Duplicate handoff_id raises ServiceError with code 'conflict'."""
    from kb.service.handoffs import create_handoff

    kwargs = dict(
        handoff_id="migrate-db:null:opencode:01",
        task_slug="migrate-db",
        role="opencode",
        handoff_seq=1,
        status="ready",
        frontmatter=VALID_FRONTMATTER,
        body_md=VALID_BODY,
        export_path=EXPORT_PATH,
        subject=None,
    )
    create_handoff(session, data_dir, **kwargs)

    with pytest.raises(ServiceError) as exc_info:
        # Change export_path to avoid that unique constraint but keep same handoff_id
        kwargs2 = dict(kwargs)
        kwargs2["export_path"] = "handoffs/2026/06/migrate-db/opencode_handoff_02.md"
        create_handoff(session, data_dir, **kwargs2)

    assert exc_info.value.code == "conflict"


def test_create_handoff_lint_failed_empty_frontmatter(data_dir: Path, session) -> None:
    """Empty frontmatter raises ServiceError with code 'lint_failed'."""
    from kb.service.handoffs import create_handoff

    with pytest.raises(ServiceError) as exc_info:
        create_handoff(
            session,
            data_dir,
            handoff_id="bad:null:opencode:01",
            task_slug="bad",
            role="opencode",
            handoff_seq=1,
            status="ready",
            frontmatter={},
            body_md=VALID_BODY,
            export_path="handoffs/2026/06/bad/opencode_handoff_01.md",
            subject=None,
        )

    err = exc_info.value
    assert err.code == "lint_failed"
    assert "errors" in err.detail


def test_create_handoff_lint_failed_bad_frontmatter(data_dir: Path, session) -> None:
    """Frontmatter missing required keys raises ServiceError lint_failed."""
    from kb.service.handoffs import create_handoff

    with pytest.raises(ServiceError) as exc_info:
        create_handoff(
            session,
            data_dir,
            handoff_id="bad:null:opencode:01",
            task_slug="bad",
            role="opencode",
            handoff_seq=1,
            status="ready",
            frontmatter={"task_slug": "bad"},  # missing required keys
            body_md=VALID_BODY,
            export_path="handoffs/2026/06/bad/opencode_handoff_01.md",
            subject=None,
        )

    assert exc_info.value.code == "lint_failed"


def test_create_handoff_with_explicit_timestamps(data_dir: Path, session) -> None:
    """created_at and updated_at are stored when provided."""
    from kb.service.handoffs import create_handoff

    result = create_handoff(
        session,
        data_dir,
        handoff_id="migrate-db:null:opencode:01",
        task_slug="migrate-db",
        role="opencode",
        handoff_seq=1,
        status="ready",
        frontmatter=VALID_FRONTMATTER,
        body_md=VALID_BODY,
        export_path=EXPORT_PATH,
        subject=None,
        created_at="2026-06-01T00:00:00+09:00",
        updated_at="2026-06-01T00:00:00+09:00",
    )

    assert result["export"]["status"] == "success"
    row = session.execute(
        select(Handoff).where(Handoff.handoff_id == "migrate-db:null:opencode:01")
    ).scalar_one()
    assert row.created_at == "2026-06-01T00:00:00+09:00"
    assert row.updated_at == "2026-06-01T00:00:00+09:00"
