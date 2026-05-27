from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from kb.db import make_engine


@pytest.fixture()
def migrated_engine(tmp_path: Path):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    import os
    os.environ["KB_DATA_DIR"] = str(tmp_path)
    command.upgrade(cfg, "head")
    return make_engine(tmp_path)


def _tables(engine) -> set[str]:
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).all()
    return {r[0] for r in rows}


def test_pages_tables_exist(migrated_engine):
    assert {"pages", "page_tags", "page_sources", "page_aliases"} <= _tables(
        migrated_engine
    )


def test_review_status_presence_check(migrated_engine):
    # summary must have NULL review_status; entity must have non-NULL.
    with migrated_engine.begin() as c:
        with pytest.raises(Exception):
            c.execute(
                text(
                    "INSERT INTO pages(stem,rel_path,type,review_status,created,updated)"
                    " VALUES('s1','summaries/x.md','summary','approved','2026-05-01','2026-05-01')"
                )
            )


def test_wiki_edits_field_accepts_new_fields(migrated_engine):
    with migrated_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO wiki_edits(page_stem,field,edited_at,source)"
                " VALUES('p','aliases','2026-05-01T00:00:00+09:00','cli')"
            )
        )
