"""Tests for DB-canonical write helpers/routes without TestClient transport."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import json

import pytest
import yaml
from fastapi import HTTPException
from sqlalchemy import select

from kb.cli.db_api import markdown_page_payload
from kb.db.models import (
    Handoff,
    MetricsRecord,
    OperationLog,
    Page,
    PageRevision,
)
from kb.web.routes import db_canonical


def _request(data_dir: Path, token: str | None = "test-token"):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(config=SimpleNamespace(data_dir=data_dir))
        ),
    )


def test_write_api_requires_bearer(data_dir: Path, session) -> None:
    body = db_canonical.PageCreateBody(
        slug="x",
        type="concept",
        body_md="\n# X\n",
        frontmatter={"type": "concept"},
        export_path="wiki/concepts/x.md",
    )
    with pytest.raises(HTTPException) as exc:
        db_canonical.create_page(body, _request(data_dir, token=None), session)
    assert exc.value.status_code == 401


def test_create_page_writes_db_revision_and_export(data_dir: Path, session) -> None:
    payload = {
        "slug": "db-canonical-page",
        "type": "concept",
        "body_md": "\n# DB Canonical Page\n\nBody.\n",
        "frontmatter": {
            "type": "concept",
            "review_status": "not_processed",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["db"],
        },
        "export_path": "wiki/concepts/db-canonical-page.md",
    }
    resp = db_canonical.create_page(
        db_canonical.PageCreateBody(**payload), _request(data_dir), session
    )
    assert resp["export"]["status"] == "success"

    exported = data_dir / "wiki/concepts/db-canonical-page.md"
    assert exported.exists()
    fm = yaml.safe_load(exported.read_text().split("---", 2)[1])
    assert fm == payload["frontmatter"]

    page = session.execute(
        select(Page).where(Page.slug == "db-canonical-page")
    ).scalar_one()
    revision = session.execute(
        select(PageRevision).where(PageRevision.page_id == page.id)
    ).scalar_one()
    assert revision.change_kind == "create"


def test_create_page_accepts_cli_source(data_dir: Path, session) -> None:
    payload = {
        "slug": "cli-sourced-page",
        "type": "summary",
        "body_md": "\n# CLI Sourced\n\nWritten by a deterministic daily-report CLI job.\n",
        "frontmatter": {
            "type": "summary",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["usage"],
        },
        "export_path": "wiki/summaries/2026/06/cli-sourced-page.md",
        "source": "cli",
    }
    db_canonical.create_page(
        db_canonical.PageCreateBody(**payload), _request(data_dir), session
    )
    page = session.execute(
        select(Page).where(Page.slug == "cli-sourced-page")
    ).scalar_one()
    revision = session.execute(
        select(PageRevision).where(PageRevision.page_id == page.id)
    ).scalar_one()
    assert revision.source == "cli"


def test_create_page_upsert_replaces_existing_slug(data_dir: Path, session) -> None:
    payload = {
        "slug": "daily-usage",
        "type": "summary",
        "body_md": "\n# Daily Usage\n\nFirst body, long enough to clear the stub threshold easily.\n",
        "frontmatter": {
            "type": "summary",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["usage"],
        },
        "export_path": "wiki/summaries/2026/06/daily-usage.md",
        "source": "cli",
    }
    db_canonical.create_page(
        db_canonical.PageCreateBody(**payload), _request(data_dir), session
    )

    payload2 = dict(payload)
    payload2["body_md"] = (
        "\n# Daily Usage\n\nSecond body, also comfortably past the stub threshold.\n"
    )
    resp = db_canonical.create_page(
        db_canonical.PageCreateBody(**payload2), _request(data_dir), session
    )
    assert resp["export"]["status"] == "success"

    pages = (
        session.execute(select(Page).where(Page.slug == "daily-usage")).scalars().all()
    )
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

    exported = (data_dir / payload["export_path"]).read_text()
    assert "Second body" in exported


def test_metrics_upsert_keeps_single_row_per_date_type(data_dir: Path, session) -> None:
    first = db_canonical.MetricsBody(
        report_date="2026-06-04",
        report_type="opencode",
        token_total=100,
        metrics_json={"token_total": 100},
    )
    db_canonical.create_metrics(first, _request(data_dir), session)

    second = db_canonical.MetricsBody(
        report_date="2026-06-04",
        report_type="opencode",
        token_total=250,
        metrics_json={"token_total": 250},
    )
    db_canonical.create_metrics(second, _request(data_dir), session)

    rows = (
        session.execute(
            select(MetricsRecord).where(
                MetricsRecord.report_date == "2026-06-04",
                MetricsRecord.report_type == "opencode",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].token_total == 250

    exported = data_dir / "ops/reports/2026/06/2026-06-04-opencode-usage.metrics.json"
    assert json.loads(exported.read_text()) == {"token_total": 250}


def test_patch_preserves_columns_when_frontmatter_omits_keys(
    data_dir: Path, session
) -> None:
    create = {
        "slug": "patch-target",
        "type": "summary",
        "body_md": "\n# Patch Target\n\nA summary page with category and review_status set.\n",
        "frontmatter": {
            "type": "summary",
            "category": "usage",
            "review_status": "approved",
            "created": "2026-06-04",
            "updated": "2026-06-04",
            "sources": [],
            "tags": ["usage"],
        },
        "export_path": "wiki/summaries/2026/06/patch-target.md",
    }
    db_canonical.create_page(
        db_canonical.PageCreateBody(**create), _request(data_dir), session
    )

    # PATCH with a valid frontmatter that omits category and review_status.
    new_fm = {
        "type": "summary",
        "created": "2026-06-04",
        "updated": "2026-06-05",
        "sources": [],
        "tags": ["usage"],
    }
    db_canonical.patch_page(
        "patch-target",
        db_canonical.PagePatchBody(frontmatter=new_fm),
        _request(data_dir),
        session,
    )

    page = session.execute(select(Page).where(Page.slug == "patch-target")).scalar_one()
    assert page.category == "usage"
    assert page.review_status == "approved"


def test_ttl_sweep_rejects_stale_not_processed_page(data_dir: Path, session) -> None:
    create = {
        "slug": "stale-page",
        "type": "concept",
        "body_md": "\n# Stale Page\n\nA not_processed concept old enough to be swept by TTL.\n",
        "frontmatter": {
            "type": "concept",
            "review_status": "not_processed",
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "sources": [],
            "tags": ["stale"],
        },
        "export_path": "wiki/concepts/stale-page.md",
    }
    db_canonical.create_page(
        db_canonical.PageCreateBody(**create), _request(data_dir), session
    )

    resp = db_canonical.ttl_sweep(_request(data_dir), days=7, session=session)
    assert resp["swept"] == 1

    page = session.execute(select(Page).where(Page.slug == "stale-page")).scalar_one()
    assert page.review_status == "rejected"
    assert page.export_path == "rejected/concepts/stale-page.md"


def test_handoff_and_operation_log_export(data_dir: Path, session) -> None:
    handoff_payload = {
        "handoff_id": "migrate-db:null:opencode:01",
        "task_slug": "migrate-db",
        "subject": None,
        "role": "opencode",
        "handoff_seq": 1,
        "status": "ready",
        "frontmatter": {
            "handoff_id": "migrate-db:null:opencode:01",
            "task_slug": "migrate-db",
            "subject": None,
            "role": "opencode",
            "handoff_seq": 1,
            "status": "ready",
            "security": {"contains_secrets": False, "redaction_status": "none"},
            "promotion": None,
        },
        "body_md": "\n# Handoff\n\n## 1. Assignment\n\n## 2. Context received\n\n## 3. Work performed\n\n## 4. Tool trace\n\n## 5. Findings / decisions\n\n## 6. Outputs\n\n## 7. Verification\n\n## 8. Risks / uncertainties\n\n## 9. Next handoff instructions\n\n## 10. Promotion candidates\n\nDone.\n",
        "export_path": "handoffs/2026/06/migrate-db/opencode_handoff_01.md",
    }
    resp = db_canonical.create_handoff(
        db_canonical.HandoffBody(**handoff_payload), _request(data_dir), session
    )
    assert resp["export"]["status"] == "success"

    log_payload = {
        "log_date": "2026-06-04",
        "category": "migration",
        "body_md": "## 2026-06-04 (migration)\n\n- **done**: DB canonical write\n",
    }
    resp = db_canonical.create_operation_log(
        db_canonical.OperationLogBody(**log_payload), _request(data_dir), session
    )
    assert resp["export"]["status"] == "success"

    assert (data_dir / handoff_payload["export_path"]).exists()
    assert "DB canonical write" in (data_dir / "log.md").read_text()
    assert session.execute(select(Handoff)).scalar_one().handoff_id
    assert session.execute(select(OperationLog)).scalar_one().category == "migration"


def test_markdown_page_payload_preserves_frontmatter_and_body() -> None:
    markdown = """---
type: summary
subtype: daily
date: "2026-06-04"
sources: []
tags: [agent-usage]
---

# Daily Report

Body.
"""
    payload = markdown_page_payload(
        markdown=markdown,
        export_path="wiki/summaries/2026/06/2026-06-04-usage.md",
        slug="2026-06-04-usage",
        origin="generated",
        source="test",
    )
    assert payload["frontmatter"] == {
        "type": "summary",
        "subtype": "daily",
        "date": "2026-06-04",
        "sources": [],
        "tags": ["agent-usage"],
    }
    assert payload["body_md"].startswith("\n\n# Daily Report")
    assert payload["export_path"] == "wiki/summaries/2026/06/2026-06-04-usage.md"
