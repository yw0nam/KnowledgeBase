"""Tests for kb_mcp.core.graph — loading and traversal."""
from pathlib import Path

import pytest


def test_load_graph_returns_networkx_digraph(sample_graph_path):
    import networkx as nx
    from kb_mcp.core.graph import load_graph

    G = load_graph(sample_graph_path)

    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() == 5
    assert G.number_of_edges() == 4


def test_load_graph_missing_file_raises(tmp_path):
    from kb_mcp.core.graph import load_graph

    with pytest.raises(FileNotFoundError):
        load_graph(tmp_path / "does_not_exist.json")


def test_find_start_nodes_matches_label_tokens(sample_graph):
    from kb_mcp.core.graph import find_start_nodes

    start = find_start_nodes(sample_graph, "TTS engine", top_n=3)

    assert "n1" in start  # "TTS engine" exact match ranks first
    # "PR 42 add TTS support" also matches "TTS"
    assert "n2" in start


def test_find_start_nodes_no_match_returns_empty(sample_graph):
    from kb_mcp.core.graph import find_start_nodes

    assert find_start_nodes(sample_graph, "nonexistentterm", top_n=3) == []


def test_find_start_nodes_ignores_single_char_tokens(sample_graph):
    from kb_mcp.core.graph import find_start_nodes

    # Single-char tokens like "a" would otherwise match too many nodes
    result = find_start_nodes(sample_graph, "a", top_n=3)
    assert result == []


def test_bfs_collects_reachable_within_depth(sample_graph):
    from kb_mcp.core.graph import bfs

    nodes, edges = bfs(sample_graph, ["n1"], depth=1)

    # n1 -> n2 and n1 -> n3 at depth 1
    assert nodes == {"n1", "n2", "n3"}
    assert ("n1", "n2") in edges
    assert ("n1", "n3") in edges


def test_bfs_expands_further_with_greater_depth(sample_graph):
    from kb_mcp.core.graph import bfs

    nodes, _ = bfs(sample_graph, ["n1"], depth=3)

    # Depth 2 reaches n5 via n3 -> n5 and via n2 -> n5
    assert "n5" in nodes


def test_dfs_visits_all_reachable(sample_graph):
    from kb_mcp.core.graph import dfs

    nodes, _ = dfs(sample_graph, ["n1"], max_depth=6)

    # n1 -> {n2, n3} -> n5 all reachable; n4 isolated
    assert nodes == {"n1", "n2", "n3", "n5"}
    assert "n4" not in nodes


def test_format_output_includes_start_and_nodes(sample_graph):
    from kb_mcp.core.graph import bfs, format_output

    nodes, edges = bfs(sample_graph, ["n1"], depth=1)
    out = format_output(
        sample_graph, "TTS engine", "bfs", ["n1"], nodes, edges, budget=2000
    )

    assert "BFS" in out
    assert "TTS engine" in out
    assert "NODE" in out
    assert "EDGE" in out


def test_format_output_respects_budget(sample_graph):
    from kb_mcp.core.graph import bfs, format_output

    nodes, edges = bfs(sample_graph, ["n1"], depth=3)
    out = format_output(
        sample_graph, "TTS", "bfs", ["n1"], nodes, edges, budget=10
    )

    # budget=10 tokens => ~40 chars; truncation marker appended
    assert "truncated" in out


def test_search_end_to_end(sample_graph_path):
    from kb_mcp.core.graph import search

    out = search(
        question="TTS engine",
        mode="bfs",
        budget=2000,
        graph_path=sample_graph_path,
    )

    assert "TTS engine" in out
    assert "BFS" in out


def test_search_no_match_returns_informative_message(sample_graph_path):
    from kb_mcp.core.graph import search

    out = search(
        question="zzzzzznonexistentzzzzz",
        mode="bfs",
        budget=2000,
        graph_path=sample_graph_path,
    )

    assert "No matching" in out or "no match" in out.lower()


def test_search_dfs_mode(sample_graph_path):
    from kb_mcp.core.graph import search

    out = search(
        question="TTS engine",
        mode="dfs",
        budget=2000,
        graph_path=sample_graph_path,
    )

    assert "DFS" in out


def test_search_invalid_mode_raises(sample_graph_path):
    from kb_mcp.core.graph import search

    with pytest.raises(ValueError):
        search(
            question="TTS",
            mode="invalid",
            budget=2000,
            graph_path=sample_graph_path,
        )
