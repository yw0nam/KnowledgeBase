"""Tests for kb_mcp.cli.lint_handoff."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import kb_mcp.cli.lint_handoff as lh


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip("\n"))


def _valid_handoff_fm(
    role: str = "research",
    seq: int = 1,
    secrets: bool = False,
    promotion: str | None = None,
) -> str:
    promotion_repr = "null" if promotion is None else promotion
    return dedent(
        f"""
        ---
        handoff_id: "task-foo:null:{role}:{seq:02d}"
        task_slug: "task-foo"
        subject: null
        role: "{role}"
        handoff_seq: {seq}
        status: draft
        security:
          contains_secrets: {str(secrets).lower()}
          redaction_status: unchecked
        promotion: {promotion_repr}
        ---

        ## 1. Assignment

        ## 2. Context received
    """
    ).lstrip("\n")


def test_valid_handoff_passes(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    _write(task_dir / "research_handoff_01.md", _valid_handoff_fm())
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert result.errors == [], result.errors


def test_missing_role_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    fm = _valid_handoff_fm()
    fm = fm.replace('role: "research"\n', "")
    _write(task_dir / "research_handoff_01.md", fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any("role" in e.lower() for e in result.errors), result.errors


def test_invalid_status_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    fm = _valid_handoff_fm()
    fm = fm.replace("status: draft", "status: garbage")
    _write(task_dir / "research_handoff_01.md", fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any("status" in e.lower() for e in result.errors), result.errors


def test_secrets_in_final_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    _write(task_dir / "research_handoff_01.md", _valid_handoff_fm(secrets=True))
    final_fm = dedent(
        """
        ---
        type: handoff_final
        task_slug: "task-foo"
        subject: null
        finalized_at: "2026-05-08"
        source_handoffs: ["task-foo:null:research:01"]
        promotion: null
        security:
          contains_secrets: false
          redaction_status: unchecked
        tags: []
        ---

        # Final
    """
    ).lstrip("\n")
    _write(task_dir / "task-foo_final.md", final_fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any("secret" in e.lower() for e in result.errors), result.errors


def test_filename_role_mismatch_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    _write(task_dir / "execution_handoff_01.md", _valid_handoff_fm(role="research"))
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any(
        "filename" in e.lower() or "mismatch" in e.lower() for e in result.errors
    ), result.errors


def test_empty_handoffs_dir_no_errors(tmp_path):
    handoffs = tmp_path / "data" / "raw" / "handoffs"
    handoffs.mkdir(parents=True)
    result = lh.LintResult()
    lh.lint(result, handoffs)
    assert result.errors == []
    assert result.warnings == []


def test_missing_handoffs_dir_no_crash(tmp_path):
    result = lh.LintResult()
    lh.lint(result, tmp_path / "does" / "not" / "exist")
    assert result.errors == []


def test_promotion_memory_with_unchecked_redaction_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    fm = _valid_handoff_fm(promotion="memory")
    _write(task_dir / "research_handoff_01.md", fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any(
        "memory" in e.lower() and "redaction" in e.lower() for e in result.errors
    ), result.errors


def test_promotion_wiki_entity_with_secrets_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    fm = _valid_handoff_fm(promotion="wiki_entity", secrets=True)
    _write(task_dir / "research_handoff_01.md", fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any(
        "wiki_entity" in e.lower() and "secret" in e.lower() for e in result.errors
    ), result.errors


def test_handoff_id_format_invalid_errors(tmp_path):
    task_dir = tmp_path / "data" / "raw" / "handoffs" / "2026" / "05" / "task-foo"
    fm = _valid_handoff_fm()
    fm = fm.replace(
        'handoff_id: "task-foo:null:research:01"',
        'handoff_id: "BAD_FORMAT"',
    )
    _write(task_dir / "research_handoff_01.md", fm)
    result = lh.LintResult()
    lh.lint(result, tmp_path / "data" / "raw" / "handoffs")
    assert any("handoff_id" in e.lower() for e in result.errors), result.errors
