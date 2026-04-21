"""Shared pytest fixtures for kb_mcp tests."""
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_graph_path() -> Path:
    return FIXTURE_DIR / "sample_graph.json"


@pytest.fixture
def sample_graph(sample_graph_path):
    from kb_mcp.core.graph import load_graph
    return load_graph(sample_graph_path)
