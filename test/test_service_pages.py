"""Tests for kb.service.pages — plain-function service layer for Page operations.

Covers the 7 minimum scenarios required by Task 3:
1. create → export success, file on disk, DB row, create revision
2. source passes through to revision.source
3. upsert replaces slug → single Page, revisions [create, update], body_md in changed_fields, file updated
4. patch preserves category/review_status when frontmatter omits them
5. promote/approve happy path + guard (approve from not_processed → conflict)
6. reject from not_processed → rejected, export_path rewritten
7. ttl_sweep rejects stale not_processed page
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from kb.db.models import Page, PageRevision
from kb.service.pages import (
    approve_page,
    patch_page,
    promote_page,
    reject_page,
    ttl_sweep,
    upsert_page,
)
from kb.service.errors import ServiceError

# ---------------------------------------------------------------------------
# Helpers / shared payloads
# ---------------------------------------------------------------------------

_CONCEPT_FM = {
    "type": "concept",
    "review_status": "not_processed",
    "created": "2026-06-04",
    "updated": "2026-06-04",
    "sources": [],
    "tags": ["db"],
}

_SUMMARY_FM = {
    "type": "summary",
    "created": "2026-06-04",
    "updated": "2026-06-04",
    "sources": [],
    "tags": ["usage"],
}

_SUMMARY_FM_WITH_META = {
    "type": "summary",
    "category": "usage",
    "review_status": "approved",
    "created": "2026-06-04",
    "updated": "2026-06-04",
    "sources": [],
    "tags": ["usage"],
}


def _upsert_concept(session, data_dir, *, slug="test-concept", fm=None, body_md=None):
    return upsert_page(
        session,
        data_dir,
        slug=slug,
        type="concept",
        body_md=body_md or f"\n# {slug.title()}\n\nBody.\n",
        frontmatter=fm or dict(_CONCEPT_FM),
        export_path=f"wiki/concepts/{slug}.md",
    )


def _upsert_summary(session, data_dir, *, slug="test-summary", fm=None, body_md=None):
    return upsert_page(
        session,
        data_dir,
        slug=slug,
        type="summary",
        body_md=body_md or f"\n# {slug.title()}\n\nBody.\n",
        frontmatter=fm or dict(_SUMMARY_FM),
        export_path=f"wiki/summaries/2026/06/{slug}.md",
    )


# ---------------------------------------------------------------------------
# 1. create → export success, file on disk, DB row, create revision
# ---------------------------------------------------------------------------


def test_create_exports_file_and_creates_revision(data_dir: Path, session) -> None:
    fm = {
        "type": "concept",
        "review_status": "not_processed",
        "created": "2026-06-04",
        "updated": "2026-06-04",
        "sources": [],
        "tags": ["db"],
    }
    body_md = "\n# DB Canonical Page\n\nBody.\n"
    result = upsert_page(
        session,
        data_dir,
        slug="db-canonical-page",
        type="concept",
        body_md=body_md,
        frontmatter=fm,
        export_path="wiki/concepts/db-canonical-page.md",
    )

    assert result["export"]["status"] == "success"

    exported = data_dir / "wiki/concepts/db-canonical-page.md"
    assert exported.exists()
    parsed_fm = yaml.safe_load(exported.read_text().split("---", 2)[1])
    assert parsed_fm == fm

    page = session.execute(
        select(Page).where(Page.slug == "db-canonical-page")
    ).scalar_one()
    revision = session.execute(
        select(PageRevision).where(PageRevision.page_id == page.id)
    ).scalar_one()
    assert revision.change_kind == "create"


# ---------------------------------------------------------------------------
# 2. source passes through to revision.source
# ---------------------------------------------------------------------------


def test_create_source_propagates_to_revision(data_dir: Path, session) -> None:
    _upsert_summary(
        session,
        data_dir,
        slug="cli-sourced-page",
        fm={
            "type": "summary",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["usage"],
        },
    )
    # call again with explicit source to get the revision
    upsert_page(
        session,
        data_dir,
        slug="cli-sourced-page2",
        type="summary",
        body_md="\n# CLI Sourced\n\nWritten by a deterministic daily-report CLI job.\n",
        frontmatter={
            "type": "summary",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["usage"],
        },
        export_path="wiki/summaries/2026/06/cli-sourced-page2.md",
        source="cli",
    )

    page = session.execute(
        select(Page).where(Page.slug == "cli-sourced-page2")
    ).scalar_one()
    revision = session.execute(
        select(PageRevision).where(PageRevision.page_id == page.id)
    ).scalar_one()
    assert revision.source == "cli"


# ---------------------------------------------------------------------------
# 3. upsert replaces existing slug → single Page, revisions [create, update],
#    body_md in changed_fields, exported file updated
# ---------------------------------------------------------------------------


def test_upsert_replaces_slug(data_dir: Path, session) -> None:
    fm = dict(_SUMMARY_FM)
    slug = "daily-usage"
    export_path = f"wiki/summaries/2026/06/{slug}.md"

    upsert_page(
        session,
        data_dir,
        slug=slug,
        type="summary",
        body_md="\n# Daily Usage\n\nFirst body, long enough to clear the stub threshold easily.\n",
        frontmatter=fm,
        export_path=export_path,
        source="cli",
    )

    result = upsert_page(
        session,
        data_dir,
        slug=slug,
        type="summary",
        body_md="\n# Daily Usage\n\nSecond body, also comfortably past the stub threshold.\n",
        frontmatter=fm,
        export_path=export_path,
        source="cli",
    )
    assert result["export"]["status"] == "success"

    pages = session.execute(select(Page).where(Page.slug == slug)).scalars().all()
    assert len(pages) == 1
    assert "Second body" in pages[0].body_md

    revisions = (
        session.execute(
            select(PageRevision)
            .where(PageRevision.page_id == pages[0].id)
            .order_by(PageRevision.revision_number)
        )
        .scalars()
        .all()
    )
    assert [r.change_kind for r in revisions] == ["create", "update"]
    assert "body_md" in (revisions[1].changed_fields or {})

    exported = (data_dir / export_path).read_text()
    assert "Second body" in exported


# ---------------------------------------------------------------------------
# 4. patch preserves category/review_status when frontmatter omits them
# ---------------------------------------------------------------------------


def test_patch_preserves_columns_when_frontmatter_omits_keys(
    data_dir: Path, session
) -> None:
    fm = dict(_SUMMARY_FM_WITH_META)
    upsert_page(
        session,
        data_dir,
        slug="patch-target",
        type="summary",
        body_md="\n# Patch Target\n\nA summary page with category and review_status set.\n",
        frontmatter=fm,
        export_path="wiki/summaries/2026/06/patch-target.md",
    )

    new_fm = {
        "type": "summary",
        "created": "2026-06-04",
        "updated": "2026-06-05",
        "sources": [],
        "tags": ["usage"],
    }
    patch_page(
        session,
        data_dir,
        slug="patch-target",
        frontmatter=new_fm,
    )

    page = session.execute(select(Page).where(Page.slug == "patch-target")).scalar_one()
    assert page.category == "usage"
    assert page.review_status == "approved"


# ---------------------------------------------------------------------------
# 5. promote/approve happy path + guard
# ---------------------------------------------------------------------------


def test_promote_and_approve_happy_path(data_dir: Path, session) -> None:
    _upsert_concept(session, data_dir, slug="promote-me")

    result = promote_page(session, data_dir, slug="promote-me")
    page = session.execute(select(Page).where(Page.slug == "promote-me")).scalar_one()
    assert page.review_status == "pending_for_approve"
    assert result["page"]["review_status"] == "pending_for_approve"

    result = approve_page(session, data_dir, slug="promote-me")
    page = session.execute(select(Page).where(Page.slug == "promote-me")).scalar_one()
    assert page.review_status == "approved"
    assert "approved_at" in page.frontmatter


def test_approve_from_not_processed_raises_conflict(data_dir: Path, session) -> None:
    _upsert_concept(session, data_dir, slug="skip-promote")

    with pytest.raises(ServiceError) as exc_info:
        approve_page(session, data_dir, slug="skip-promote")
    assert exc_info.value.code == "conflict"


# ---------------------------------------------------------------------------
# 6. reject from not_processed → rejected, export_path rewritten
# ---------------------------------------------------------------------------


def test_reject_from_not_processed(data_dir: Path, session) -> None:
    _upsert_concept(session, data_dir, slug="reject-me")

    result = reject_page(session, data_dir, slug="reject-me")

    page = session.execute(select(Page).where(Page.slug == "reject-me")).scalar_one()
    assert page.review_status == "rejected"
    assert page.export_path == "rejected/concepts/reject-me.md"
    assert result["page"]["review_status"] == "rejected"


# ---------------------------------------------------------------------------
# 7. ttl_sweep rejects stale not_processed page
# ---------------------------------------------------------------------------


def test_ttl_sweep_rejects_stale_page(data_dir: Path, session) -> None:
    fm = {
        "type": "concept",
        "review_status": "not_processed",
        "created": "2026-01-01",
        "updated": "2026-01-01",
        "sources": [],
        "tags": ["stale"],
    }
    upsert_page(
        session,
        data_dir,
        slug="stale-page",
        type="concept",
        body_md="\n# Stale Page\n\nA not_processed concept old enough to be swept by TTL.\n",
        frontmatter=fm,
        export_path="wiki/concepts/stale-page.md",
    )

    result = ttl_sweep(session, data_dir, days=7)
    assert result["swept"] == 1

    page = session.execute(select(Page).where(Page.slug == "stale-page")).scalar_one()
    assert page.review_status == "rejected"
    assert page.export_path == "rejected/concepts/stale-page.md"
