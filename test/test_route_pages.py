"""Backend route tests for ``GET /api/pages/{stem}``.

The Decisions browser opens a focused page detail on row click and
expects the same shape as ``/api/queue`` entries (frontmatter + body)
for any ``review_status`` — not just pending.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from kb import REPO_ROOT


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _write_page(
    data_dir: Path,
    rel: str,
    fm: dict,
    body: str = "Body paragraph for the page.\n",
) -> Path:
    path = data_dir / "wiki" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_block = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{fm_block}---\n\n# {path.stem}\n\n{body}")
    return path


def _entity_fm(**over) -> dict:
    fm = {
        "type": "entity",
        "review_status": "approved",
        "created": "2026-05-26",
        "updated": "2026-05-26",
        "sources": [],
        "tags": [],
    }
    fm.update(over)
    return fm


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "wiki").mkdir(parents=True)
    (d / "raw").mkdir(parents=True)
    return d


@pytest.fixture()
def client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    command.upgrade(_alembic_cfg(), "head")
    from kb.web.app import create_app

    return TestClient(create_app())


def test_get_page_returns_frontmatter_and_body(
    client: TestClient, data_dir: Path
) -> None:
    page = _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(review_status="approved", category="system-ops"),
        body="Distinctive body line.\n",
    )

    resp = client.get("/api/pages/Foo-page")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stem"] == "Foo-page"
    assert body["rel_path"] == "entities/Foo/2026-05/Foo-page.md"
    assert body["abs_path"] == str(page)
    assert body["frontmatter"]["review_status"] == "approved"
    assert body["frontmatter"]["category"] == "system-ops"
    assert "Distinctive body line." in body["body"]
    # Body must NOT include the frontmatter fence.
    assert "---" not in body["body"].splitlines()[0]


def test_get_page_unknown_stem_returns_404(client: TestClient, data_dir: Path) -> None:
    _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(),
    )

    resp = client.get("/api/pages/does-not-exist")
    assert resp.status_code == 404, resp.text
    assert "does-not-exist" in resp.json()["detail"]
