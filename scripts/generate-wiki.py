#!/usr/bin/env python3
"""
Generate curated wiki pages from graph.json.

Reads graphify-out/graph.json and generates:
- wiki/entities/ — one page per god node (project, tool, person)
- wiki/concepts/ — one page per community cluster
- wiki/index.md — index of all pages

Run after `/graphify raw/` completes.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any

BASEDIR = Path(__file__).parent.parent
GRAPH_FILE = BASEDIR / "graphify-out" / "graph.json"
WIKI_DIR = BASEDIR / "wiki"
ENTITIES_DIR = WIKI_DIR / "entities"
CONCEPTS_DIR = WIKI_DIR / "concepts"
NOW = datetime.utcnow().strftime("%Y-%m-%d")


def normalize_name(label: str) -> str:
    """Convert label to filename-safe PascalCase or Snake_Case."""
    # For entities (projects, tools, people): PascalCase
    # For concepts (abstract ideas): Snake_Case
    label = label.strip()
    if label.startswith("PR #") or label.endswith(".md"):
        # Entity-like (PR, file)
        name = re.sub(r"[^a-zA-Z0-9\s]", "", label).replace(" ", "")
        return name
    elif any(word in label.lower() for word in ["chain", "gate", "flow", "system"]):
        # Entity-like (patterns with clear names)
        words = label.split()
        return "".join(w.capitalize() for w in words if w)
    else:
        # Concept-like (abstract)
        return label.replace(" ", "_").replace("-", "_")


def extract_sources(node: dict) -> list:
    """Extract source_file from node, return as list."""
    sources = []
    if "source_file" in node:
        sources.append(node["source_file"])
    return sources


def extract_graph_nodes(community: int, nodes: list) -> list:
    """Get node IDs for a given community."""
    return [n.get("id", "") for n in nodes if n.get("community") == community]


def render_entity_page(node: dict, related_nodes: list) -> str:
    """Generate a curated entity page from a god node."""
    label = node["label"]
    sources = extract_sources(node)

    # Extract PR number if present
    pr_match = re.search(r"PR #(\d+)", label)
    pr_num = pr_match.group(1) if pr_match else None

    # Related nodes (neighbors in graph)
    related_links = "\n".join(
        f"- [[{normalize_name(n['label'])}]]"
        for n in related_nodes[:5]
        if n["id"] != node["id"]
    )

    sources_yaml = "\n  - ".join(sources) if sources else ""

    return f"""---
type: entity
created: "{NOW}"
updated: "{NOW}"
sources:
  - {sources_yaml}
graph_nodes:
  - "{node['id']}"
tags: [entity]
---

# {label}

## Overview

## Key Details

## Related

{related_links if related_links else "_(none yet)_"}
"""


def render_concept_page(community: int, nodes: list) -> str:
    """Generate a concept page from a community cluster."""
    # Find most connected nodes in this community
    community_nodes = [n for n in nodes if n.get("community") == community]

    if not community_nodes:
        return ""

    # Sort by node degree (connections)
    community_nodes.sort(key=lambda n: n.get("degree", 0), reverse=True)
    top_nodes = community_nodes[:5]

    node_links = "\n".join(
        f"- [[{normalize_name(n['label'])}]]"
        for n in top_nodes
    )

    sources = list(set(
        src for n in community_nodes
        for src in extract_sources(n)
        if src
    ))
    sources_yaml = "\n  - ".join(sources) if sources else ""

    concept_name = f"Community_{community}"

    return f"""---
type: concept
created: "{NOW}"
updated: "{NOW}"
sources:
  - {sources_yaml}
graph_nodes:
  - {', '.join(f'"{n["id"]}"' for n in community_nodes)}
tags: [concept, cluster]
---

# {concept_name}

Community cluster with {len(community_nodes)} nodes.

## Key Nodes

{node_links}

## Related Concepts

_(to be filled in)_
"""


def load_graph() -> dict:
    """Load graph.json."""
    if not GRAPH_FILE.exists():
        print(f"Error: {GRAPH_FILE} not found. Run `/graphify raw/` first.")
        exit(1)

    with open(GRAPH_FILE) as f:
        return json.load(f)


def build_adjacency(graph: dict) -> dict:
    """Build node ID -> neighbors map."""
    adj = {}
    edges = graph.get("links", [])

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")

        if src not in adj:
            adj[src] = []
        if tgt not in adj:
            adj[tgt] = []

        adj[src].append(tgt)
        adj[tgt].append(src)

    return adj


def main():
    print("Generating wiki from graph.json...")

    graph = load_graph()
    nodes_list = graph.get("nodes", [])

    if not nodes_list:
        print("Error: No nodes in graph.json")
        exit(1)

    # Build adjacency for neighbor lookup
    adj = build_adjacency(graph)

    # Add degree to each node
    for node in nodes_list:
        node["degree"] = len(adj.get(node.get("id", ""), []))

    # Create directories
    ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Generate entity pages from god nodes ---
    # God nodes = highest degree nodes (manually set or by centrality)
    sorted_nodes = sorted(nodes_list, key=lambda n: n.get("degree", 0), reverse=True)
    god_nodes = sorted_nodes[:8]  # Top 8 nodes

    entity_pages = []
    for node in god_nodes:
        filename = normalize_name(node["label"]) + ".md"
        filepath = ENTITIES_DIR / filename

        # Get neighbors for "Related" section
        neighbors = [
            n for n in nodes_list
            if n["id"] in adj.get(node["id"], [])
        ]

        content = render_entity_page(node, neighbors)
        filepath.write_text(content)

        entity_pages.append((filename, node["label"]))
        print(f"  Created {filepath}")

    # --- Generate concept pages from communities ---
    communities = set(n.get("community") for n in nodes_list if "community" in n)
    communities = sorted(c for c in communities if c is not None)

    concept_pages = []
    for comm in communities[:10]:  # Limit to first 10 communities
        filename = f"Community_{comm}.md"
        filepath = CONCEPTS_DIR / filename

        content = render_concept_page(comm, nodes_list)
        if content:
            filepath.write_text(content)
            concept_pages.append((filename, f"Community {comm}"))
            print(f"  Created {filepath}")

    # --- Update wiki/index.md ---
    entities_section = "\n".join(
        f"- [[{name}|{label}]]"
        for name, label in entity_pages
    )

    concepts_section = "\n".join(
        f"- [[{name}|{label}]]"
        for name, label in concept_pages
    )

    index_content = f"""---
type: index
created: "{NOW}"
updated: "{NOW}"
---

# KnowledgeBase Index

Generated from graph.json on {NOW}.

## Entities (God Nodes)

{entities_section}

## Concepts (Communities)

{concepts_section}

## Summaries

_(to be generated)_

## Decisions

- [[001-vault-structure]] - 3-layer LLM Wiki architecture

## Questions

_(from queries)_
"""

    (WIKI_DIR / "index.md").write_text(index_content)
    print(f"  Updated {WIKI_DIR / 'index.md'}")

    print(f"\n✓ Wiki generation complete: {len(entity_pages)} entities, {len(concept_pages)} concepts")


if __name__ == "__main__":
    main()
