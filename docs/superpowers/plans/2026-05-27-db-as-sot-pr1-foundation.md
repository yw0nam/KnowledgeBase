# DB-as-SOT Inversion — PR1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the canonical frontmatter store in `state.db` (four new tables), the shared frontmatter write core, and the `kb-page import`/`render` CLI — populating the DB from existing markdown and normalizing every `.md` to a generated frontmatter block, while nothing yet *reads* from the DB (fully reversible, inert).

**Architecture:** Frontmatter becomes single-home canonical in SQLite; the markdown body stays file-SOT; the `.md` frontmatter block is regenerated from the DB row by a deterministic serializer carrying a `# managed-by: kb-page` marker. A single canonical field map (`_fields.py`) drives both parse (md → DB) and render (DB → md) so the round-trip is lossless. `kb-page import --all` is an idempotent upsert-by-stem that doubles as the repair path.

**Tech Stack:** Python 3, SQLAlchemy + Alembic (SQLite, WAL), PyYAML, pytest. Matches existing patterns in `src/kb/db/` and `alembic/versions/53cdbd2e163d_*`.

**Spec:** `docs/superpowers/specs/2026-05-27-db-as-sot-inversion-design.md` (§2 schema, §3 identity, §4 write core, §5 render, §7 migration). Reviewer-LGTM'd (Database Optimizer + Backend Architect).

**Scope boundary:** PR1 introduces the DB + write core + import/render only. Console PATCH cutover (PR3), `kb-page create/set` authoring verbs and the lint split (PR2), and skills/hook (PR4) are out of scope. The `apply_frontmatter_change` core lands here but is exercised only by `import`/`render` in this PR.

---

## File Structure

- Create `alembic/versions/<rev>_pages_and_join_tables.py` — the four tables + `wiki_edits` CHECK widening.
- Create `src/kb/cli/page/__init__.py` — `kb-page` CLI entry (`import`, `render` subcommands only in PR1).
- Create `src/kb/cli/page/_fields.py` — canonical field map: typed columns, join fields, render order; the single SOT shared by parse + render.
- Create `src/kb/cli/page/_serialize.py` — `parse_frontmatter(fm: dict) -> ParsedPage` and `render_block(page: ParsedPage) -> str`.
- Create `src/kb/db/repos/page_repo.py` — `upsert_page`, `get_by_stem`, `delete_by_stem`, join-row replace helpers.
- Create `src/kb/cli/page/_core.py` — `apply_frontmatter_change` + `render_page_file` (DB→disk).
- Modify `src/kb/db/models.py` — add `Page`, `PageTag`, `PageSource`, `PageAlias`.
- Modify `src/kb/db/__init__.py` — export the four new models in `__all__`.
- Modify `pyproject.toml` — add `kb-page = "kb.cli.page:main"` to `[project.scripts]`.
- Tests under `test/` (existing test dir; mirror `test/test_db_init.py` fixtures).

---

## Task 1: Alembic migration — four tables + widen `wiki_edits`

**Files:**
- Create: `alembic/versions/<rev>_pages_and_join_tables.py` (generate `<rev>` with the command below)
- Test: `test/test_pages_schema.py`

- [ ] **Step 1: Generate an empty revision to get a real revision id + correct `down_revision`**

Run:
```bash
cd /home/spow12/codes/KnowledgeBase/.claude/worktrees/feat+kanban-phase-3-hermes
KB_DATA_DIR=/tmp/kb-plan-data uv run alembic revision -m "pages and join tables"
```
Expected: prints `Generating .../alembic/versions/<rev>_pages_and_join_tables.py ... done`. Open the file; it already has `revision`, `down_revision = "53cdbd2e163d"`. Keep those.

- [ ] **Step 2: Write the failing schema test**

Create `test/test_pages_schema.py`:
```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `KB_DATA_DIR=/tmp/kb-x uv run pytest test/test_pages_schema.py -v`
Expected: FAIL — tables missing / inserts succeed where they should raise.

- [ ] **Step 4: Implement the migration**

Replace the generated `upgrade()`/`downgrade()` bodies with (keep the generated header/revision lines):
```python
def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pages (
            id            INTEGER PRIMARY KEY,
            stem          TEXT NOT NULL UNIQUE,
            rel_path      TEXT NOT NULL UNIQUE,
            type          TEXT NOT NULL
                          CHECK (type IN ('entity','concept','decision','question',
                                          'improvement','checklist','summary')),
            subtype       TEXT
                          CHECK (subtype IS NULL OR subtype IN ('weekly','monthly','daily')),
            category      TEXT,
            review_status TEXT
                          CHECK (review_status IS NULL OR
                                 review_status IN ('not_processed','pending_for_approve','approved')),
            period_start  TEXT CHECK (period_start IS NULL OR period_start LIKE '____-__-__%'),
            period_end    TEXT CHECK (period_end   IS NULL OR period_end   LIKE '____-__-__%'),
            created       TEXT NOT NULL,
            updated       TEXT NOT NULL,
            extra         JSON CHECK (extra IS NULL OR json_valid(extra)),
            CHECK (
              (type IN ('entity','concept','decision','improvement','checklist','question')
                 AND review_status IS NOT NULL)
              OR (type = 'summary' AND review_status IS NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_pages_type_review_status ON pages(type, review_status)")
    op.execute(
        "CREATE INDEX ix_pages_review_status ON pages(review_status) "
        "WHERE review_status IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_pages_type_category ON pages(type, category)")
    op.execute(
        "CREATE INDEX ix_pages_period_end ON pages(period_end DESC) WHERE type = 'summary'"
    )

    op.execute(
        """
        CREATE TABLE page_tags (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            tag     TEXT NOT NULL,
            UNIQUE(page_id, tag)
        )
        """
    )
    op.execute("CREATE INDEX ix_page_tags_tag ON page_tags(tag)")

    op.execute(
        """
        CREATE TABLE page_sources (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            source  TEXT NOT NULL,
            UNIQUE(page_id, source)
        )
        """
    )
    op.execute("CREATE INDEX ix_page_sources_source ON page_sources(source)")

    op.execute(
        """
        CREATE TABLE page_aliases (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            alias   TEXT NOT NULL,
            UNIQUE(page_id, alias)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_page_aliases_alias ON page_aliases(alias)")

    # Widen wiki_edits.field + source to cover the new editable fields and the
    # CLI write source. SQLite can't ALTER a CHECK, so rebuild via the
    # 12-step table-rebuild (here: new table + copy + swap).
    op.execute(
        """
        CREATE TABLE wiki_edits_new (
            id        INTEGER PRIMARY KEY,
            page_stem TEXT NOT NULL,
            field     TEXT NOT NULL
                      CHECK (field IN ('review_status','type','category','tags',
                                       'sources','aliases','subtype',
                                       'period_start','period_end','extra')),
            old_value JSON CHECK (old_value IS NULL OR json_valid(old_value)),
            new_value JSON CHECK (new_value IS NULL OR json_valid(new_value)),
            edited_at TEXT NOT NULL
                      CHECK (edited_at LIKE '____-__-__T__:__:__+09:00'),
            source    TEXT NOT NULL DEFAULT 'console'
                      CHECK (source IN ('console','migration','cli'))
        )
        """
    )
    op.execute(
        "INSERT INTO wiki_edits_new "
        "SELECT id,page_stem,field,old_value,new_value,edited_at,source FROM wiki_edits"
    )
    op.execute("DROP TABLE wiki_edits")
    op.execute("ALTER TABLE wiki_edits_new RENAME TO wiki_edits")
    op.execute(
        "CREATE INDEX ix_wiki_edits_page_stem_edited_at "
        "ON wiki_edits(page_stem, edited_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_wiki_edits_review_status_transitions "
        "ON wiki_edits(edited_at) WHERE field = 'review_status'"
    )
    op.execute(
        """
        CREATE TRIGGER trg_wiki_edits_no_update
        BEFORE UPDATE ON wiki_edits
        BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_wiki_edits_no_delete
        BEFORE DELETE ON wiki_edits
        BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS page_aliases")
    op.execute("DROP TABLE IF EXISTS page_sources")
    op.execute("DROP TABLE IF EXISTS page_tags")
    op.execute("DROP TABLE IF EXISTS pages")
    # wiki_edits left in its widened form on downgrade — acceptable; the
    # widened CHECK is a strict superset and PR1 is the only consumer.
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `KB_DATA_DIR=/tmp/kb-y uv run pytest test/test_pages_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/*_pages_and_join_tables.py test/test_pages_schema.py
git commit -m "feat(db): pages + join tables migration; widen wiki_edits.field"
```

---

## Task 2: ORM models + exports

**Files:**
- Modify: `src/kb/db/models.py`
- Modify: `src/kb/db/__init__.py`
- Test: `test/test_pages_models.py`

- [ ] **Step 1: Write the failing test**

Create `test/test_pages_models.py`:
```python
from kb.db import Page, PageAlias, PageSource, PageTag


def test_models_importable_and_tablenames():
    assert Page.__tablename__ == "pages"
    assert PageTag.__tablename__ == "page_tags"
    assert PageSource.__tablename__ == "page_sources"
    assert PageAlias.__tablename__ == "page_aliases"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_pages_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Page'`.

- [ ] **Step 3: Add the models**

Append to `src/kb/db/models.py` (after `WikiEdit`):
```python
class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stem: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    rel_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    period_start: Mapped[str | None] = mapped_column(String, nullable=True)
    period_end: Mapped[str | None] = mapped_column(String, nullable=True)
    created: Mapped[str] = mapped_column(String, nullable=False)
    updated: Mapped[str] = mapped_column(String, nullable=False)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PageTag(Base):
    __tablename__ = "page_tags"

    page_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String, primary_key=True)


class PageSource(Base):
    __tablename__ = "page_sources"

    page_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)


class PageAlias(Base):
    __tablename__ = "page_aliases"

    page_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(String, primary_key=True)
```
(Composite PKs on the join models match the table `UNIQUE(page_id, x)`; the real FK/cascade lives in the migration DDL, which is SOT.)

- [ ] **Step 4: Export from `__init__.py`**

In `src/kb/db/__init__.py`, update the import and `__all__`:
```python
from kb.db.models import (
    Base,
    Dispatch,
    Page,
    PageAlias,
    PageSource,
    PageTag,
    WikiEdit,
)
```
and add `"Page"`, `"PageTag"`, `"PageSource"`, `"PageAlias"` to the `__all__` list.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest test/test_pages_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kb/db/models.py src/kb/db/__init__.py test/test_pages_models.py
git commit -m "feat(db): Page/PageTag/PageSource/PageAlias ORM models"
```

---

## Task 3: Canonical field map (`_fields.py`)

**Files:**
- Create: `src/kb/cli/page/__init__.py` (empty for now — package marker; `main` added in Task 7)
- Create: `src/kb/cli/page/_fields.py`
- Test: `test/test_page_fields.py`

- [ ] **Step 1: Create the package marker**

Create empty `src/kb/cli/page/__init__.py` (one line):
```python
"""kb-page CLI: DB-canonical frontmatter authoring + render/import."""
```

- [ ] **Step 2: Write the failing test**

Create `test/test_page_fields.py`:
```python
from kb.cli.page._fields import (
    JOIN_FIELDS,
    TYPED_COLUMNS,
    RENDER_ORDER,
)


def test_typed_columns_and_join_fields_disjoint():
    assert set(TYPED_COLUMNS).isdisjoint(set(JOIN_FIELDS))


def test_render_order_covers_typed_and_join():
    for k in TYPED_COLUMNS:
        assert k in RENDER_ORDER
    for k in JOIN_FIELDS:
        assert k in RENDER_ORDER
    # 'stem' is identity (filename), never a rendered frontmatter key
    assert "stem" not in RENDER_ORDER
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest test/test_page_fields.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `_fields.py`**

```python
"""Single source of truth for the frontmatter <-> DB field mapping.

Both parse (md -> DB) and render (DB -> md) import from here so the
round-trip is lossless. Any top-level frontmatter key that is NOT a
typed column and NOT a join field falls into the JSON ``extra`` column.
"""

from __future__ import annotations

# Typed columns on the ``pages`` table (excludes id/stem/rel_path/extra).
TYPED_COLUMNS: tuple[str, ...] = (
    "type",
    "subtype",
    "category",
    "review_status",
    "period_start",
    "period_end",
    "created",
    "updated",
)

# Multi-valued frontmatter keys -> join table names.
JOIN_FIELDS: dict[str, str] = {
    "tags": "page_tags",
    "sources": "page_sources",
    "aliases": "page_aliases",
}

# Deterministic key order for the rendered block. Keys absent on a page
# are skipped at render time. ``extra`` keys are emitted, sorted, in the
# EXTRA_SLOT position.
EXTRA_SLOT = "__extra__"
RENDER_ORDER: tuple[str, ...] = (
    "type",
    "subtype",
    "category",
    "review_status",
    "period_start",
    "period_end",
    "tags",
    "sources",
    "aliases",
    EXTRA_SLOT,
    "created",
    "updated",
)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest test/test_page_fields.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kb/cli/page/__init__.py src/kb/cli/page/_fields.py test/test_page_fields.py
git commit -m "feat(page): canonical frontmatter<->DB field map"
```

---

## Task 4: Parse + render (`_serialize.py`)

**Files:**
- Create: `src/kb/cli/page/_serialize.py`
- Test: `test/test_page_serialize.py`

- [ ] **Step 1: Write the failing round-trip test**

Create `test/test_page_serialize.py`:
```python
from kb.cli.page._serialize import ParsedPage, parse_frontmatter, render_block


def test_parse_splits_typed_join_and_extra():
    fm = {
        "type": "improvement",
        "category": "tooling",
        "review_status": "approved",
        "tags": ["a", "b"],
        "sources": ["raw/manual/x.md"],
        "severity": "high",
        "kind": "bug",
        "created": "2026-05-01",
        "updated": "2026-05-02",
    }
    p = parse_frontmatter(fm)
    assert p.typed["type"] == "improvement"
    assert p.tags == ["a", "b"]
    assert p.sources == ["raw/manual/x.md"]
    assert p.aliases == []
    assert p.extra == {"severity": "high", "kind": "bug"}


def test_render_is_deterministic_and_marked():
    p = ParsedPage(
        typed={
            "type": "concept",
            "category": "x",
            "review_status": "approved",
            "created": "2026-05-01",
            "updated": "2026-05-02",
        },
        tags=["z", "a"],
        sources=[],
        aliases=["Alt Name"],
        extra={"note": "n"},
    )
    block = render_block(p)
    assert block.startswith("# managed-by: kb-page\n")
    # type appears before created (RENDER_ORDER), tags sorted, aliases present
    assert block.index("type:") < block.index("created:")
    assert block.index("tags:") < block.index("created:")
    assert "Alt Name" in block


def test_round_trip_parse_render_parse_is_stable():
    fm = {
        "type": "entity",
        "category": "person",
        "review_status": "not_processed",
        "tags": ["x"],
        "aliases": ["Bob"],
        "created": "2026-05-01",
        "updated": "2026-05-01",
        "custom": "kept",
    }
    p1 = parse_frontmatter(fm)
    import yaml

    fm2 = yaml.safe_load(render_block(p1).split("\n", 1)[1])  # drop marker line
    p2 = parse_frontmatter(fm2)
    assert p1 == p2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_page_serialize.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `_serialize.py`**

```python
"""Frontmatter <-> ParsedPage (DB-shaped) conversion.

``parse_frontmatter`` is md -> DB; ``render_block`` is DB -> md. Both
go through ``_fields`` so they never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from kb.cli.page._fields import (
    EXTRA_SLOT,
    JOIN_FIELDS,
    RENDER_ORDER,
    TYPED_COLUMNS,
)

MARKER = "# managed-by: kb-page"


@dataclass
class ParsedPage:
    typed: dict[str, object] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)


def parse_frontmatter(fm: dict) -> ParsedPage:
    """Split a frontmatter dict into typed columns / join lists / extra."""
    typed: dict[str, object] = {}
    joins: dict[str, list[str]] = {"tags": [], "sources": [], "aliases": []}
    extra: dict[str, object] = {}
    for key, value in fm.items():
        if key in TYPED_COLUMNS:
            typed[key] = value
        elif key in JOIN_FIELDS:
            joins[key] = list(value or [])
        else:
            extra[key] = value
    return ParsedPage(
        typed=typed,
        tags=joins["tags"],
        sources=joins["sources"],
        aliases=joins["aliases"],
        extra=extra,
    )


def _dump_scalar_or_list(key: str, value: object) -> str:
    """YAML-dump a single ``key: value`` mapping, no trailing newline noise."""
    text = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True)
    return text.rstrip("\n")


def render_block(page: ParsedPage) -> str:
    """Render the deterministic frontmatter block (no surrounding fences)."""
    lines: list[str] = [MARKER]
    join_values = {"tags": page.tags, "sources": page.sources, "aliases": page.aliases}
    for slot in RENDER_ORDER:
        if slot == EXTRA_SLOT:
            for k in sorted(page.extra):
                lines.append(_dump_scalar_or_list(k, page.extra[k]))
            continue
        if slot in JOIN_FIELDS:
            vals = join_values[slot]
            if vals:
                lines.append(_dump_scalar_or_list(slot, list(vals)))
            continue
        if slot in page.typed and page.typed[slot] is not None:
            lines.append(_dump_scalar_or_list(slot, page.typed[slot]))
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_page_serialize.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kb/cli/page/_serialize.py test/test_page_serialize.py
git commit -m "feat(page): lossless frontmatter parse/render serializer"
```

---

## Task 5: `page_repo` — upsert + joins + get/delete

**Files:**
- Create: `src/kb/db/repos/page_repo.py`
- Modify: `src/kb/db/repos/__init__.py` (export `page_repo`)
- Test: `test/test_page_repo.py`

- [ ] **Step 1: Write the failing test**

Create `test/test_page_repo.py`:
```python
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo


@pytest.fixture()
def session(tmp_path: Path):
    os.environ["KB_DATA_DIR"] = str(tmp_path)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    factory = make_session_factory(make_engine(tmp_path))
    s = factory()
    yield s
    s.close()


def test_upsert_inserts_then_updates_same_stem(session):
    row = page_repo.upsert_page(
        session,
        stem="foo",
        rel_path="concepts/foo.md",
        typed={"type": "concept", "review_status": "approved",
               "created": "2026-05-01", "updated": "2026-05-01"},
        tags=["a"], sources=[], aliases=["F"], extra={"k": "v"},
    )
    assert row.id > 0
    again = page_repo.upsert_page(
        session,
        stem="foo",
        rel_path="concepts/foo.md",
        typed={"type": "concept", "review_status": "approved",
               "created": "2026-05-01", "updated": "2026-05-02"},
        tags=["a", "b"], sources=[], aliases=[], extra={},
    )
    assert again.id == row.id  # same row, not a duplicate
    assert again.updated == "2026-05-02"
    tags = page_repo.get_tags(session, again.id)
    assert tags == ["a", "b"]
    assert page_repo.get_aliases(session, again.id) == []  # replaced, not merged


def test_get_and_delete_by_stem(session):
    page_repo.upsert_page(
        session, stem="bar", rel_path="concepts/bar.md",
        typed={"type": "concept", "review_status": "approved",
               "created": "2026-05-01", "updated": "2026-05-01"},
        tags=["t"], sources=[], aliases=[], extra={},
    )
    assert page_repo.get_by_stem(session, "bar") is not None
    page_repo.delete_by_stem(session, "bar")
    assert page_repo.get_by_stem(session, "bar") is None
    # cascade cleared the tag row
    assert page_repo.get_tags(session, 1) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_page_repo.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `page_repo.py`**

```python
"""CRUD for ``pages`` + its join tables. Function-style, like the other repos.

``upsert_page`` is keyed on ``stem`` (the natural identity for import
re-runs). Join rows are REPLACED wholesale on each upsert, not merged —
the caller passes the full desired set. Cascade on the FK clears join
rows when a page is deleted.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from kb.db.models import Page, PageAlias, PageSource, PageTag

_JOIN = {"tags": PageTag, "sources": PageSource, "aliases": PageAlias}
_JOIN_COL = {"tags": PageTag.tag, "sources": PageSource.source, "aliases": PageAlias.alias}


def get_by_stem(session: Session, stem: str) -> Page | None:
    return session.execute(
        select(Page).where(Page.stem == stem)
    ).scalar_one_or_none()


def _replace_join(session: Session, page_id: int, kind: str, values: Sequence[str]) -> None:
    model = _JOIN[kind]
    session.execute(delete(model).where(model.page_id == page_id))
    seen: set[str] = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        session.add(model(page_id=page_id, **{_field(kind): v}))


def _field(kind: str) -> str:
    return {"tags": "tag", "sources": "source", "aliases": "alias"}[kind]


def _get_join(session: Session, page_id: int, kind: str) -> list[str]:
    col = _JOIN_COL[kind]
    model = _JOIN[kind]
    rows = session.execute(
        select(col).where(model.page_id == page_id).order_by(col)
    ).scalars().all()
    return list(rows)


def get_tags(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "tags")


def get_sources(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "sources")


def get_aliases(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "aliases")


def upsert_page(
    session: Session,
    *,
    stem: str,
    rel_path: str,
    typed: dict,
    tags: Sequence[str],
    sources: Sequence[str],
    aliases: Sequence[str],
    extra: dict,
) -> Page:
    """Insert or update the page row keyed on ``stem``; replace join rows."""
    row = get_by_stem(session, stem)
    if row is None:
        row = Page(stem=stem, rel_path=rel_path)
        session.add(row)
    row.rel_path = rel_path
    for col in ("type", "subtype", "category", "review_status",
                "period_start", "period_end", "created", "updated"):
        setattr(row, col, typed.get(col))
    row.extra = extra or None
    session.flush()  # assigns row.id for the join writes
    _replace_join(session, row.id, "tags", tags)
    _replace_join(session, row.id, "sources", sources)
    _replace_join(session, row.id, "aliases", aliases)
    session.commit()
    session.refresh(row)
    return row


def delete_by_stem(session: Session, stem: str) -> None:
    """Delete the page; FK cascade clears join rows."""
    row = get_by_stem(session, stem)
    if row is None:
        return
    # Ensure cascade fires (PRAGMA foreign_keys is ON per kb.db engine).
    session.execute(text("PRAGMA foreign_keys = ON"))
    session.delete(row)
    session.commit()
```

- [ ] **Step 4: Export from repos `__init__.py`**

In `src/kb/db/repos/__init__.py` add `page_repo` to the imports/`__all__` (match the existing `dispatch_repo`/`wiki_edit_repo` entries).

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest test/test_page_repo.py -v`
Expected: PASS (2 tests). If the cascade assertion fails, confirm `_set_sqlite_pragmas` ran (it does on every connect in `kb.db`).

- [ ] **Step 6: Commit**

```bash
git add src/kb/db/repos/page_repo.py src/kb/db/repos/__init__.py test/test_page_repo.py
git commit -m "feat(db): page_repo upsert-by-stem + join replace + cascade delete"
```

---

## Task 6: Write core + render-to-file (`_core.py`)

**Files:**
- Create: `src/kb/cli/page/_core.py`
- Test: `test/test_page_core.py`

The PR1 surface of the core is `render_page_file` (DB row → on-disk `.md` with regenerated block + preserved body) and `ingest_file` (parse a `.md`, upsert into DB, then render). `apply_frontmatter_change` (field-change + audit) is stubbed here and fully wired in PR2/PR3; PR1 only needs ingest+render. We add the change-function signature now so later PRs import a stable name.

- [ ] **Step 1: Write the failing test**

Create `test/test_page_core.py`:
```python
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo
from kb.cli.page._core import ingest_file, render_page_file


@pytest.fixture()
def env(tmp_path: Path):
    os.environ["KB_DATA_DIR"] = str(tmp_path)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_page_core.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `_core.py`**

```python
"""Shared frontmatter write core: ingest (md->DB) and render (DB->md).

The body is never owned by the DB — render replaces only the frontmatter
block and re-attaches the original body verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from kb.cli.page._serialize import parse_frontmatter, render_block
from kb.cli.wiki_review._store import _split_frontmatter, resolve_stem
from kb.db.repos import page_repo


def _read_split(path: Path) -> tuple[dict, str]:
    """Return (frontmatter dict, body) for a wiki page file."""
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm = yaml.safe_load(parts[0]) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    return fm, parts[1]


def _write_with_block(path: Path, block: str, body: str) -> None:
    body = body.lstrip("\n")
    path.write_text(f"---\n{block}---\n\n{body}")


def ingest_file(session: Session, *, wiki_dir: Path, path: Path) -> None:
    """Parse ``path``, upsert into the DB, then re-render its block."""
    fm, body = _read_split(path)
    parsed = parse_frontmatter(fm)
    stem = path.stem
    rel_path = str(path.relative_to(wiki_dir))
    page_repo.upsert_page(
        session,
        stem=stem,
        rel_path=rel_path,
        typed=parsed.typed,
        tags=parsed.tags,
        sources=parsed.sources,
        aliases=parsed.aliases,
        extra=parsed.extra,
    )
    _write_with_block(path, render_block(parsed), body)


def render_page_file(session: Session, *, wiki_dir: Path, stem: str) -> None:
    """Regenerate the frontmatter block of ``stem`` from the DB row."""
    row = page_repo.get_by_stem(session, stem)
    if row is None:
        raise ValueError(f"no pages row for stem {stem!r}")
    path = resolve_stem(wiki_dir, stem)
    _, body = _read_split(path)
    parsed = parse_frontmatter(
        {
            "type": row.type,
            "subtype": row.subtype,
            "category": row.category,
            "review_status": row.review_status,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "created": row.created,
            "updated": row.updated,
            "tags": page_repo.get_tags(session, row.id),
            "sources": page_repo.get_sources(session, row.id),
            "aliases": page_repo.get_aliases(session, row.id),
            **(row.extra or {}),
        }
    )
    # Drop None typed values so they don't render as empty keys.
    parsed.typed = {k: v for k, v in parsed.typed.items() if v is not None}
    _write_with_block(path, render_block(parsed), body)


def apply_frontmatter_change(
    session: Session,
    *,
    stem: str,
    changes: Sequence[tuple[str, object, object]],
    source: str,
    wiki_dir: Path,
) -> None:
    """Field-change + audit + re-render. Fully wired in PR2/PR3.

    PR1 ships the signature only so later PRs import a stable name; it is
    not called by import/render and raises if invoked.
    """
    raise NotImplementedError("apply_frontmatter_change lands in PR2/PR3")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest test/test_page_core.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kb/cli/page/_core.py test/test_page_core.py
git commit -m "feat(page): ingest (md->DB) + idempotent render-to-file core"
```

---

## Task 7: `kb-page` CLI — `import` + `render`

**Files:**
- Modify: `src/kb/cli/page/__init__.py` (add `main`)
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `test/test_page_cli.py`

- [ ] **Step 1: Write the failing test**

Create `test/test_page_cli.py`:
```python
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.cli.page import main
from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo


@pytest.fixture()
def wiki(tmp_path: Path):
    os.environ["KB_DATA_DIR"] = str(tmp_path)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest test/test_page_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'main'`.

- [ ] **Step 3: Implement `main` in `src/kb/cli/page/__init__.py`**

```python
"""kb-page CLI: DB-canonical frontmatter authoring + render/import.

PR1 subcommands: ``import`` (md -> DB + normalize files) and ``render``
(regenerate block from DB). Authoring verbs (``create``/``set``) land in
PR2.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from kb import REPO_ROOT
from kb.cli.page._core import _read_split, ingest_file, render_page_file
from kb.cli.page._serialize import parse_frontmatter, render_block
from kb.db import make_engine, make_session_factory


def _data_dir() -> Path:
    return Path(os.environ.get("KB_DATA_DIR", REPO_ROOT / "data")).resolve()


def _wiki_dir(data_dir: Path) -> Path:
    return data_dir / "wiki"


def _iter_wiki_files(wiki_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(wiki_dir.rglob("*.md"))
        if p.name not in ("_index.md", "INDEX.md")
    ]


def _roundtrip_ok(path: Path) -> bool:
    """True if re-rendering the file's parsed frontmatter is YAML-equal."""
    fm, _ = _read_split(path)
    parsed = parse_frontmatter(fm)
    rendered = render_block(parsed)
    reparsed = yaml.safe_load(rendered.split("\n", 1)[1]) or {}
    return parse_frontmatter(reparsed) == parsed


def _cmd_import(args: argparse.Namespace) -> int:
    data_dir = _data_dir()
    wiki_dir = _wiki_dir(data_dir)
    files = _iter_wiki_files(wiki_dir) if args.all else [Path(args.path).resolve()]

    failures: list[str] = []
    for p in files:
        try:
            if not _roundtrip_ok(p):
                failures.append(f"roundtrip mismatch: {p.relative_to(wiki_dir)}")
        except Exception as exc:  # noqa: BLE001 — report-and-continue gate
            failures.append(f"parse error: {p}: {exc}")
    if failures:
        print("DRY-RUN GATE FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"dry-run OK: {len(files)} pages would import")
        return 0

    factory = make_session_factory(make_engine(data_dir))
    session = factory()
    try:
        for p in files:
            ingest_file(session, wiki_dir=wiki_dir, path=p)
    finally:
        session.close()
    print(f"imported {len(files)} pages")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    data_dir = _data_dir()
    wiki_dir = _wiki_dir(data_dir)
    factory = make_session_factory(make_engine(data_dir))
    session = factory()
    try:
        if args.all:
            from kb.db.models import Page
            from sqlalchemy import select

            stems = list(session.execute(select(Page.stem)).scalars().all())
        else:
            stems = [args.stem]
        for stem in stems:
            render_page_file(session, wiki_dir=wiki_dir, stem=stem)
    finally:
        session.close()
    print(f"rendered {len(stems)} pages")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb-page")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="ingest markdown frontmatter into the DB")
    g = imp.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("path", nargs="?")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=_cmd_import)

    ren = sub.add_parser("render", help="regenerate the frontmatter block from the DB")
    rg = ren.add_mutually_exclusive_group(required=True)
    rg.add_argument("--all", action="store_true")
    rg.add_argument("stem", nargs="?")
    ren.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    return args.func(args)
```

- [ ] **Step 4: Register the entry point**

In `pyproject.toml` `[project.scripts]`, add:
```toml
kb-page = "kb.cli.page:main"
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest test/test_page_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add src/kb/cli/page/__init__.py pyproject.toml test/test_page_cli.py
git commit -m "feat(page): kb-page import (idempotent + dry-run) and render CLI"
```

---

## Task 8: Full-suite + lint gate, then live dry-run rehearsal

**Files:** none (verification task)

- [ ] **Step 1: Run the whole backend suite**

Run: `uv run pytest -q`
Expected: all pass (existing ~162 + the new PR1 tests). Fix any regressions before proceeding.

- [ ] **Step 2: Run the repo lint**

Run: `./scripts/lint.sh`
Expected: all checks PASS (ruff/format/types). Fix and re-run until clean.

- [ ] **Step 3: Dry-run against the REAL wiki (read-only — no DB write, no file write)**

Run:
```bash
KB_DATA_DIR=/home/spow12/codes/KnowledgeBase/data uv run kb-page import --all --dry-run
```
Expected: `dry-run OK: N pages would import`, OR a `DRY-RUN GATE FAILED` list. If failures: do NOT proceed to a real import — capture the list, fix the serializer/field-map (Tasks 3-4) for the offending shapes, re-run. This is the §7 zero-loss gate; a real import is only safe when dry-run is clean.

- [ ] **Step 4: Record the dry-run outcome (no commit if clean)**

If the dry-run surfaced shapes the field-map doesn't cover (e.g. an unanticipated multi-valued key), add a follow-up note to the PR description. Do not hand-edit `data/`. The real `import --all` (which writes the live DB + normalizes files) is an operator step run deliberately after this PR merges, with `git diff data/wiki` reviewed to confirm body-only-untouched + block-normalized — per spec §7 verification + rollback.

---

## Self-Review (completed by plan author)

**Spec coverage (PR1 slice of §10):** migration+4 tables (Task 1), `wiki_edits` widening (Task 1), ORM+export (Task 2), field map (Task 3), lossless parse/render incl. marker §5 (Task 4), upsert-by-stem + cascade §2.5/§4.4-delete-primitive (Task 5), ingest+idempotent render core §4/§5 (Task 6), `import --all` idempotent + `--dry-run` roundtrip gate §7 (Task 7), suite+lint+live dry-run rehearsal §7-verification (Task 8). The `apply_frontmatter_change` change-path body, console PATCH cutover, authoring verbs, lint split, and skills/hook are explicitly deferred to PR2-4 (header scope boundary).

**Placeholder scan:** no TBD/TODO; every code step carries complete code. The one deliberate stub (`apply_frontmatter_change`) raises `NotImplementedError` by design and is documented as a PR2/PR3 deliverable, not a placeholder.

**Type consistency:** `ParsedPage` fields (`typed/tags/sources/aliases/extra`) are identical across Tasks 4/5/6/7; `parse_frontmatter`/`render_block`/`upsert_page(stem,rel_path,typed,tags,sources,aliases,extra)`/`ingest_file`/`render_page_file` signatures match every call site; `_fields` constants (`TYPED_COLUMNS`, `JOIN_FIELDS`, `RENDER_ORDER`, `EXTRA_SLOT`) are referenced consistently. `_read_split` is defined in `_core.py` and imported by the CLI — single definition.
