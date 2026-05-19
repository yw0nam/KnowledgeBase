"""Tests for kb-wiki-review CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb_mcp.cli.wiki_review import _store


def _write_page(path: Path, fm: dict, body: str = "Body. " * 20) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines))


def test_resolve_stem_unique(tmp_path):
    wiki = tmp_path / "wiki"
    _write_page(
        wiki / "entities" / "Subj" / "2026-05" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    assert _store.resolve_stem(wiki, "Foo").name == "Foo.md"


def test_resolve_stem_collision_errors(tmp_path):
    wiki = tmp_path / "wiki"
    _write_page(
        wiki / "entities" / "A" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    _write_page(
        wiki / "entities" / "B" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    with pytest.raises(_store.StemCollision) as exc:
        _store.resolve_stem(wiki, "Foo")
    assert "entities/A/Foo.md" in str(exc.value)
    assert "entities/B/Foo.md" in str(exc.value)


def test_resolve_stem_not_found(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    with pytest.raises(_store.PageNotFound):
        _store.resolve_stem(wiki, "Nope")


def test_set_field_updates_existing(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "review_status: not_processed\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    _store.set_frontmatter_field(p, "review_status", "approved")
    text = p.read_text()
    assert "review_status: approved\n" in text
    assert "review_status: not_processed" not in text
    assert "type: entity\n" in text  # unrelated fields preserved


def test_set_field_appends_when_missing(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    _store.set_frontmatter_field(p, "review_status", "pending_for_approve")
    text = p.read_text()
    assert "review_status: pending_for_approve\n" in text
    # Field is appended inside frontmatter (before closing ---), order preserved.
    fm_block = text.split("---")[1]
    assert "type: entity" in fm_block
    assert "review_status: pending_for_approve" in fm_block


def test_get_field_reads_value(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "review_status: approved\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    assert _store.get_frontmatter_field(p, "review_status") == "approved"
    assert _store.get_frontmatter_field(p, "type") == "entity"
    assert _store.get_frontmatter_field(p, "missing") is None
