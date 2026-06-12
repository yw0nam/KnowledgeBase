"""Tests for kb.service.sources — create_raw_source.

TDD: these tests must fail first (module doesn't exist yet), then pass after
implementation.  Tests exercise the service API directly against a real
Postgres test database via the conftest fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from kb.db.models import RawSource
from kb.service.errors import ServiceError


def test_create_raw_source_returns_id_and_export(session, data_dir: Path) -> None:
    """Happy path: returns dict with id, source_key, and successful export."""
    from kb.service.sources import create_raw_source

    result = create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/x.md",
        source_type="manual",
        content_md="# Title\n\nbody",
    )

    assert isinstance(result["id"], int)
    assert result["source_key"] == "raw/manual/x.md"
    assert result["export"]["status"] == "success"
    assert isinstance(result["export"]["written"], int)


def test_create_raw_source_writes_db_row(session, data_dir: Path) -> None:
    """A RawSource row must exist in the DB after creation."""
    from kb.service.sources import create_raw_source

    create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/db-row.md",
        source_type="manual",
        content_md="# DB Row\n\ncontent",
    )

    row = session.execute(
        select(RawSource).where(RawSource.source_key == "raw/manual/db-row.md")
    ).scalar_one()
    assert row.source_key == "raw/manual/db-row.md"
    assert row.source_type == "manual"


def test_create_raw_source_exports_markdown_file(session, data_dir: Path) -> None:
    """The exported Markdown file must exist under data_dir with the body."""
    from kb.service.sources import create_raw_source

    create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/x.md",
        source_type="manual",
        content_md="# Title\n\nbody",
    )

    exported = data_dir / "raw/manual/x.md"
    assert exported.exists()
    text = exported.read_text()
    assert "# Title" in text
    assert "body" in text


def test_create_raw_source_title_defaults_to_first_heading(
    session, data_dir: Path
) -> None:
    """When title is None, the first H1 line becomes the title."""
    from kb.service.sources import create_raw_source

    create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/heading.md",
        source_type="manual",
        content_md="# My Heading\n\nsome content",
        title=None,
    )

    row = session.execute(
        select(RawSource).where(RawSource.source_key == "raw/manual/heading.md")
    ).scalar_one()
    assert row.title == "My Heading"


def test_create_raw_source_title_explicit_overrides_heading(
    session, data_dir: Path
) -> None:
    """An explicit title param beats the first-heading fallback."""
    from kb.service.sources import create_raw_source

    create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/explicit.md",
        source_type="manual",
        content_md="# Heading\n\ncontent",
        title="Explicit Title",
    )

    row = session.execute(
        select(RawSource).where(RawSource.source_key == "raw/manual/explicit.md")
    ).scalar_one()
    assert row.title == "Explicit Title"


def test_create_raw_source_conflict_raises_service_error(
    session, data_dir: Path
) -> None:
    """Calling create_raw_source twice with the same source_key raises ServiceError(conflict)."""
    from kb.service.sources import create_raw_source

    create_raw_source(
        session,
        data_dir,
        source_key="raw/manual/dup.md",
        source_type="manual",
        content_md="# Dup\n\nfirst",
    )

    with pytest.raises(ServiceError) as exc_info:
        create_raw_source(
            session,
            data_dir,
            source_key="raw/manual/dup.md",
            source_type="manual",
            content_md="# Dup\n\nsecond",
        )

    assert exc_info.value.code == "conflict"
