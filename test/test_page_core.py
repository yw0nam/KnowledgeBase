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


def test_ingest_and_render_converge_for_quoted_dates(env):
    # The real wiki writes quoted dates; ingest and render must produce
    # identical bytes, otherwise files flip quoting forever.
    data_dir, wiki, factory = env
    page = wiki / "concepts" / "q.md"
    page.write_text(
        "---\ntype: concept\nreview_status: approved\n"
        'created: "2026-05-25"\nupdated: "2026-05-25"\n---\n\n# Q\n\nbody\n'
    )
    s = factory()
    ingest_file(s, wiki_dir=wiki, path=page)
    after_ingest = page.read_text()
    render_page_file(s, wiki_dir=wiki, stem="q")
    after_render = page.read_text()
    assert after_ingest == after_render
    s.close()


def test_unquoted_date_in_extra_does_not_crash(env):
    data_dir, wiki, factory = env
    (wiki / "improvements").mkdir(parents=True, exist_ok=True)
    page = wiki / "improvements" / "imp.md"
    page.write_text(
        "---\ntype: improvement\nreview_status: approved\n"
        "observed_at: 2026-05-25\n"  # unquoted -> would be a date object
        "created: 2026-05-25\nupdated: 2026-05-25\n---\n\n# Imp\n\nbody\n"
    )
    s = factory()
    ingest_file(s, wiki_dir=wiki, path=page)  # must not raise
    row = page_repo.get_by_stem(s, "imp")
    assert row.extra["observed_at"] == "2026-05-25"  # stored as string
    s.close()
