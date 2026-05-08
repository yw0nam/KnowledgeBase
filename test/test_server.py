"""Tests for kb_mcp.server — tool registration and CLI."""
import pytest


async def test_build_server_registers_ingest_tool():
    from kb_mcp.server import build_server

    mcp = build_server()
    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert "kb_ingest" in names


def test_main_supports_stdio_and_http_flags(monkeypatch, capsys):
    import sys

    from kb_mcp import server

    calls = []

    def fake_run(self, transport=None, **kwargs):
        calls.append({"transport": transport, **kwargs})

    monkeypatch.setattr("fastmcp.FastMCP.run", fake_run)

    monkeypatch.setattr(sys, "argv", ["kb-mcp", "--transport", "stdio"])
    server.main()
    assert calls[-1]["transport"] == "stdio"

    monkeypatch.setattr(
        sys, "argv", ["kb-mcp", "--transport", "http", "--port", "9001"]
    )
    server.main()
    assert calls[-1]["transport"] == "streamable-http"
    assert calls[-1]["port"] == 9001
