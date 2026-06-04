"""Tests for the kb-lint CLI exit-code logic."""

from __future__ import annotations

from kb.cli.lint import _exit_code
from kb.lint.common import LintResult


def test_errors_always_fail() -> None:
    r = LintResult()
    r.error("x", "broken")
    assert _exit_code([r], strict=False) == 1
    assert _exit_code([r], strict=True) == 1


def test_warnings_only_fail_under_strict() -> None:
    r = LintResult()
    r.warn("x", "smelly")
    assert _exit_code([r], strict=False) == 0
    assert _exit_code([r], strict=True) == 1


def test_clean_passes() -> None:
    assert _exit_code([LintResult()], strict=True) == 0
