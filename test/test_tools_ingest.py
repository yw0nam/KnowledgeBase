"""Tests for kb_mcp.tools.ingest — MCP tool wrapper."""
import subprocess

import pytest
from pydantic import ValidationError


def test_ingest_input_requires_repos():
    from kb_mcp.tools.ingest import IngestInput

    with pytest.raises(ValidationError):
        IngestInput()


def test_ingest_input_rejects_empty_list():
    from kb_mcp.tools.ingest import IngestInput

    with pytest.raises(ValidationError):
        IngestInput(repos=[])


def test_ingest_input_rejects_malformed_repo():
    from kb_mcp.tools.ingest import IngestInput

    with pytest.raises(ValidationError):
        IngestInput(repos=["not-valid"])


def test_ingest_input_accepts_valid_repos():
    from kb_mcp.tools.ingest import IngestInput

    m = IngestInput(repos=["owner/repo", "a/b"])
    assert m.repos == ["owner/repo", "a/b"]


async def test_kb_ingest_runs_and_reports_success(monkeypatch, tmp_path):
    from kb_mcp.tools import ingest as ingest_tool
    from kb_mcp.tools.ingest import IngestInput

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\necho done\n")
    script.chmod(0o755)
    monkeypatch.setattr(ingest_tool, "DEFAULT_SCRIPT_PATH", script)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await ingest_tool.kb_ingest(IngestInput(repos=["owner/repo"]))

    assert "success" in result.lower() or "done" in result.lower() or "0" in result


async def test_kb_ingest_reports_failure(monkeypatch, tmp_path):
    from kb_mcp.tools import ingest as ingest_tool
    from kb_mcp.tools.ingest import IngestInput

    script = tmp_path / "ingest.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    monkeypatch.setattr(ingest_tool, "DEFAULT_SCRIPT_PATH", script)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await ingest_tool.kb_ingest(IngestInput(repos=["owner/repo"]))

    assert "error" in result.lower() or "failed" in result.lower() or "boom" in result
