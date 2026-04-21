"""Tests for kb_mcp.tools.search — MCP tool wrapper."""
import pytest
from pydantic import ValidationError


def test_search_input_requires_question():
    from kb_mcp.tools.search import SearchInput

    with pytest.raises(ValidationError):
        SearchInput()  # missing question


def test_search_input_defaults():
    from kb_mcp.tools.search import SearchInput

    m = SearchInput(question="TTS")

    assert m.mode == "bfs"
    assert m.budget == 2000


def test_search_input_rejects_invalid_mode():
    from kb_mcp.tools.search import SearchInput

    with pytest.raises(ValidationError):
        SearchInput(question="TTS", mode="random")


def test_search_input_rejects_negative_budget():
    from kb_mcp.tools.search import SearchInput

    with pytest.raises(ValidationError):
        SearchInput(question="TTS", budget=-1)


async def test_kb_search_returns_formatted_string(sample_graph_path, monkeypatch):
    from kb_mcp.tools import search as search_tool
    from kb_mcp.tools.search import SearchInput

    monkeypatch.setattr(search_tool, "DEFAULT_GRAPH_PATH", sample_graph_path)

    result = await search_tool.kb_search(
        SearchInput(question="TTS engine", mode="bfs", budget=2000)
    )

    assert isinstance(result, str)
    assert "TTS engine" in result


async def test_kb_search_propagates_no_match_message(sample_graph_path, monkeypatch):
    from kb_mcp.tools import search as search_tool
    from kb_mcp.tools.search import SearchInput

    monkeypatch.setattr(search_tool, "DEFAULT_GRAPH_PATH", sample_graph_path)

    result = await search_tool.kb_search(
        SearchInput(question="zzznoresultzzz", mode="bfs", budget=2000)
    )

    assert "No matching" in result or "no match" in result.lower()
