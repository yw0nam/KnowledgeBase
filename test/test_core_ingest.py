"""Tests for kb_mcp.core.ingest — subprocess wrapper for ingest-github.sh."""
import subprocess
from pathlib import Path

import pytest


def test_ingest_github_invokes_script_with_repos(monkeypatch, tmp_path):
    from kb_mcp.core import ingest as ingest_mod

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    result = ingest_mod.ingest_github(
        repos=["owner/repo", "owner/other"], script_path=script
    )

    assert result["returncode"] == 0
    assert "done" in result["stdout"]
    assert captured["cmd"][0] == str(script)
    assert captured["cmd"][1:] == ["owner/repo", "owner/other"]


def test_ingest_github_empty_repos_raises(tmp_path):
    from kb_mcp.core import ingest as ingest_mod

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\n")

    with pytest.raises(ValueError, match="repos"):
        ingest_mod.ingest_github(repos=[], script_path=script)


def test_ingest_github_rejects_malformed_repo(tmp_path):
    from kb_mcp.core import ingest as ingest_mod

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\n")

    with pytest.raises(ValueError, match="owner/repo"):
        ingest_mod.ingest_github(repos=["not-a-valid-repo"], script_path=script)


def test_ingest_github_missing_script_raises(tmp_path):
    from kb_mcp.core import ingest as ingest_mod

    with pytest.raises(FileNotFoundError):
        ingest_mod.ingest_github(
            repos=["owner/repo"], script_path=tmp_path / "nope.sh"
        )


def test_ingest_github_reports_nonzero_exit(monkeypatch, tmp_path):
    from kb_mcp.core import ingest as ingest_mod

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)

    result = ingest_mod.ingest_github(
        repos=["owner/repo"], script_path=script
    )

    assert result["returncode"] == 1
    assert "boom" in result["stderr"]
