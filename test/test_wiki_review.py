"""Tests for kb-wiki-review CLI."""

from __future__ import annotations

import subprocess
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
        {
            "type": "entity",
            "review_status": "not_processed",
            "created": '"2026-05-01"',
            "updated": '"2026-05-01"',
            "sources": "[]",
            "aliases": "[]",
            "tags": "[]",
        },
    )
    assert _store.resolve_stem(wiki, "Foo").name == "Foo.md"


def test_resolve_stem_collision_errors(tmp_path):
    wiki = tmp_path / "wiki"
    _write_page(
        wiki / "entities" / "A" / "Foo.md",
        {
            "type": "entity",
            "review_status": "not_processed",
            "created": '"2026-05-01"',
            "updated": '"2026-05-01"',
            "sources": "[]",
            "aliases": "[]",
            "tags": "[]",
        },
    )
    _write_page(
        wiki / "entities" / "B" / "Foo.md",
        {
            "type": "entity",
            "review_status": "not_processed",
            "created": '"2026-05-01"',
            "updated": '"2026-05-01"',
            "sources": "[]",
            "aliases": "[]",
            "tags": "[]",
        },
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
        'created: "2026-05-19"\n'
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
    p.write_text("---\n" "type: entity\n" 'created: "2026-05-19"\n' "---\n" "\nBody.\n")
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
        'created: "2026-05-19"\n'
        "---\n"
        "\nBody.\n"
    )
    assert _store.get_frontmatter_field(p, "review_status") == "approved"
    assert _store.get_frontmatter_field(p, "type") == "entity"
    assert _store.get_frontmatter_field(p, "missing") is None


def test_append_feedback_creates_section(tmp_path):
    from kb_mcp.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text("---\ntype: entity\n---\n\n# Title\n\nSome body.\n")
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


def _make_page(
    wiki: Path,
    type_: str,
    stem: str,
    status: str = "not_processed",
    created: str = "2026-05-19",
    subj: str = "subj",
) -> Path:
    """Helper to write a syntactically valid wiki page."""
    if type_ == "entity":
        path = wiki / "entities" / subj / "2026-05" / f"{stem}.md"
    else:
        path = wiki / f"{type_}s" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = ""
    if type_ == "entity":
        extra = "aliases: []\n"
    if type_ == "improvement":
        extra = (
            "kind: improvement\n"
            'observed_at: "2026-05-19"\n'
            "domain: dx\n"
            "severity: low\n"
            "issue_status: open\n"
            "related: []\n"
        )
    fm = (
        "---\n"
        f"type: {type_}\n"
        f"review_status: {status}\n"
        f"{extra}"
        f'created: "{created}"\n'
        f'updated: "{created}"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
        "\n"
        f"# {stem}\n\nBody. " * 5
    )
    path.write_text(fm)
    return path


def test_promote_transitions_to_pending(tmp_path):
    from kb_mcp.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "pending_for_approve"
    # No User Feedback section added (system action).
    assert "## User Feedback" not in page.read_text()


def test_promote_errors_when_already_pending(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 1
    captured = capsys.readouterr()
    assert "promote only from not_processed" in captured.err


def test_promote_errors_when_already_approved(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="approved")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 1
    assert "promote only from not_processed" in capsys.readouterr().err


def test_promote_errors_when_page_not_found(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    rc = _commands.cmd_promote(wiki, "Nope")
    assert rc == 1
    assert "page not found in wiki/" in capsys.readouterr().err


def test_approve_with_feedback_arg(tmp_path):
    from kb_mcp.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="Looks solid.", today="2026-05-19")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "approved"
    text = page.read_text()
    assert "## User Feedback" in text
    assert "2026-05-19-Approved: Looks solid." in text


def test_approve_empty_feedback_skips_section(tmp_path):
    from kb_mcp.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="", today="2026-05-19")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "approved"
    assert "## User Feedback" not in page.read_text()


def test_approve_errors_on_not_processed(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="x", today="2026-05-19")
    assert rc == 1
    assert "must be pending_for_approve" in capsys.readouterr().err


def test_approve_errors_on_already_approved(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="approved")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="x", today="2026-05-19")
    assert rc == 1
    assert "already approved" in capsys.readouterr().err


def _init_data_repo(data_dir: Path) -> None:
    """Init a real git repo at data_dir for git mv tests."""
    data_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=data_dir, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=data_dir,
        check=True,
    )


def test_reject_moves_file_to_rejected_tree(tmp_path):
    from kb_mcp.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    subprocess.run(["git", "add", "."], cwd=data, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "add Foo",
        ],
        cwd=data,
        check=True,
    )

    rc = _commands.cmd_reject(
        wiki_dir=wiki,
        rejected_dir=rejected,
        data_dir=data,
        stem="Foo",
        feedback="Bad sources.",
        today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00",
        rejected_by="user",
    )
    assert rc == 0
    assert not page.exists()
    moved = rejected / "entities" / "subj" / "2026-05" / "Foo.md"
    assert moved.exists()
    text = moved.read_text()
    assert "review_status: rejected" in text
    assert 'rejected_at: "2026-05-19T14:30:00+09:00"' in text
    assert "rejected_by: user" in text
    assert "2026-05-19-Rejected: Bad sources." in text


def test_reject_errors_on_not_pending(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_reject(
        wiki_dir=wiki,
        rejected_dir=data / "rejected",
        data_dir=data,
        stem="Foo",
        feedback="x",
        today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00",
        rejected_by="user",
    )
    assert rc == 1
    assert "must be pending_for_approve" in capsys.readouterr().err


def test_reject_collision_errors(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    # Pre-existing collision at the rejected destination.
    dest = rejected / "entities" / "subj" / "2026-05" / "Foo.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("already here")

    rc = _commands.cmd_reject(
        wiki_dir=wiki,
        rejected_dir=rejected,
        data_dir=data,
        stem="Foo",
        feedback="x",
        today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00",
        rejected_by="user",
    )
    assert rc == 1
    assert "already exists" in capsys.readouterr().err
    # Original wiki file untouched on collision.
    assert page.exists()


def test_list_filters_by_status(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed", created="2026-05-15")
    _make_page(wiki, "entity", "B", status="pending_for_approve", created="2026-05-16")
    _make_page(wiki, "concept", "C", status="approved", created="2026-05-17")

    rc = _commands.cmd_list(
        wiki, status="pending_for_approve", counts=False, today="2026-05-19"
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "B" in out
    assert "A" not in out
    assert "C" not in out


def test_list_all_status(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed")
    _make_page(wiki, "entity", "B", status="pending_for_approve")
    _make_page(wiki, "concept", "C", status="approved")

    rc = _commands.cmd_list(wiki, status="all", counts=False, today="2026-05-19")
    assert rc == 0
    out = capsys.readouterr().out
    assert all(s in out for s in ("A", "B", "C"))


def test_list_counts(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed")
    _make_page(wiki, "entity", "B", status="not_processed")
    _make_page(wiki, "entity", "C", status="pending_for_approve")
    _make_page(wiki, "concept", "D", status="approved")

    rc = _commands.cmd_list(wiki, status="all", counts=True, today="2026-05-19")
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 not_processed" in out
    assert "1 pending_for_approve" in out
    assert "1 approved" in out


def test_ttl_sweep_rejects_old_not_processed(tmp_path, capsys):
    from kb_mcp.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    # 8 days old → should be swept.
    old = _make_page(
        wiki, "entity", "Stale", status="not_processed", created="2026-05-11"
    )
    # 6 days old → not swept.
    young = _make_page(
        wiki, "entity", "Fresh", status="not_processed", created="2026-05-13"
    )
    # pending — not swept regardless of age.
    pending = _make_page(
        wiki, "concept", "Pending", status="pending_for_approve", created="2026-05-01"
    )
    subprocess.run(["git", "add", "."], cwd=data, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "seed",
        ],
        cwd=data,
        check=True,
    )

    rc = _commands.cmd_ttl_sweep(
        wiki_dir=wiki,
        rejected_dir=rejected,
        data_dir=data,
        days=7,
        today="2026-05-19",
        now_iso="2026-05-19T00:30:00+09:00",
    )
    assert rc == 0
    assert not old.exists()
    moved = rejected / "entities" / "subj" / "2026-05" / "Stale.md"
    assert moved.exists()
    assert "auto_ttl" in moved.read_text()
    assert "Auto-rejected" in moved.read_text()
    assert young.exists()
    assert pending.exists()


def test_main_dispatch_list(tmp_path, capsys, monkeypatch):
    from kb_mcp.cli import wiki_review

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="pending_for_approve")

    # Force REPO_ROOT to our tmp tree.
    monkeypatch.setattr("kb_mcp.cli.wiki_review._store.WIKI_DIR", wiki)
    monkeypatch.setattr(
        "kb_mcp.cli.wiki_review._store.REJECTED_DIR", tmp_path / "rejected"
    )

    rc = wiki_review.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "A" in out


def test_main_unknown_command(capsys):
    from kb_mcp.cli import wiki_review

    rc = wiki_review.main(["bogus"])
    assert rc != 0
