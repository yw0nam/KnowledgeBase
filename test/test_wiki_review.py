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


def test_append_feedback_creates_section(tmp_path):
    from kb_mcp.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text(
        "---\ntype: entity\n---\n\n# Title\n\nSome body.\n"
    )
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "Looks good.")
    text = p.read_text()
    assert "## User Feedback" in text
    assert "2026-05-19-Approved: Looks good." in text
    # Section appears at end of body.
    body = text.split("---", 2)[2]
    assert body.rstrip().endswith("2026-05-19-Approved: Looks good.")


def test_append_feedback_appends_to_existing_section(tmp_path):
    from kb_mcp.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text(
        "---\ntype: entity\n---\n\n# Title\n\nBody.\n\n"
        "## User Feedback\n\n2026-05-18-Rejected: Bad sources.\n"
    )
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "Fixed.")
    text = p.read_text()
    # Both lines present, in order, under a single header.
    assert text.count("## User Feedback") == 1
    assert "2026-05-18-Rejected: Bad sources." in text
    assert "2026-05-19-Approved: Fixed." in text
    # Order: existing first, then appended.
    assert text.index("2026-05-18") < text.index("2026-05-19")


def test_append_feedback_skip_empty_input(tmp_path):
    from kb_mcp.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    original = "---\ntype: entity\n---\n\n# Title\n\nBody.\n"
    p.write_text(original)
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "")
    # File unchanged when feedback is empty.
    assert p.read_text() == original


def test_append_feedback_strips_input_whitespace(tmp_path):
    from kb_mcp.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text("---\ntype: entity\n---\n\n# Title\n")
    _feedback.append_feedback_line(p, "2026-05-19", "Rejected", "   \n  trim me  \n")
    text = p.read_text()
    assert "2026-05-19-Rejected: trim me" in text
