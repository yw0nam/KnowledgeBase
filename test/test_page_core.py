from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo
from kb.cli.page._core import ingest_file, render_page_file


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    factory = make_session_factory(make_engine(tmp_path))
    return tmp_path, wiki, factory


def test_ingest_then_render_roundtrips_body_and_block(env):
    data_dir, wiki, factory = env
    page = wiki / "concepts" / "thing.md"
    page.write_text(
        "---\n"
        "type: concept\n"
        "review_status: approved\n"
        "tags:\n- x\n"
        "created: 2026-05-01\n"
        "updated: 2026-05-01\n"
        "---\n"
        "\n# Thing\n\nBody text with [[other]].\n"
    )
    s = factory()
    ingest_file(s, wiki_dir=wiki, path=page)
    row = page_repo.get_by_stem(s, "thing")
    assert row.type == "concept"
    assert page_repo.get_tags(s, row.id) == ["x"]

    # Body preserved, block regenerated + marked.
    text = page.read_text()
    assert "# managed-by: kb-page" in text
    assert "Body text with [[other]]." in text
    assert text.startswith("---\n")

    # render is idempotent: second render produces identical bytes.
    before = page.read_text()
    render_page_file(s, wiki_dir=wiki, stem="thing")
    assert page.read_text() == before
    s.close()
