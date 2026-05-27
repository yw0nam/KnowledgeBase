from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.cli.page import main
from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo


@pytest.fixture()
def wiki(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    w = tmp_path / "wiki" / "concepts"
    w.mkdir(parents=True)
    (w / "a.md").write_text(
        "---\ntype: concept\nreview_status: approved\n"
        "created: 2026-05-01\nupdated: 2026-05-01\n---\n\n# A\n\nbody\n"
    )
    return tmp_path


def test_import_all_populates_db_and_is_idempotent(wiki, capsys):
    rc = main(["import", "--all"])
    assert rc == 0
    factory = make_session_factory(make_engine(wiki))
    s = factory()
    assert page_repo.get_by_stem(s, "a") is not None
    s.close()
    # re-run: no duplicate, still rc 0 (idempotent / repair path)
    assert main(["import", "--all"]) == 0
    s2 = make_session_factory(make_engine(wiki))()
    from sqlalchemy import func, select
    from kb.db.models import Page
    assert s2.execute(select(func.count(Page.id))).scalar_one() == 1
    s2.close()


def test_import_dry_run_writes_nothing(wiki):
    rc = main(["import", "--all", "--dry-run"])
    assert rc == 0
    factory = make_session_factory(make_engine(wiki))
    s = factory()
    assert page_repo.get_by_stem(s, "a") is None  # dry-run: no DB write
    s.close()
