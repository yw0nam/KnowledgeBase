from kb.cli.page._serialize import ParsedPage, parse_frontmatter, render_block


def test_parse_splits_typed_join_and_extra():
    fm = {
        "type": "improvement",
        "category": "tooling",
        "review_status": "approved",
        "tags": ["a", "b"],
        "sources": ["raw/manual/x.md"],
        "severity": "high",
        "kind": "bug",
        "created": "2026-05-01",
        "updated": "2026-05-02",
    }
    p = parse_frontmatter(fm)
    assert p.typed["type"] == "improvement"
    assert p.tags == ["a", "b"]
    assert p.sources == ["raw/manual/x.md"]
    assert p.aliases == []
    assert p.extra == {"severity": "high", "kind": "bug"}


def test_render_is_deterministic_and_marked():
    p = ParsedPage(
        typed={
            "type": "concept",
            "category": "x",
            "review_status": "approved",
            "created": "2026-05-01",
            "updated": "2026-05-02",
        },
        tags=["z", "a"],
        sources=[],
        aliases=["Alt Name"],
        extra={"note": "n"},
    )
    block = render_block(p)
    assert block.startswith("# managed-by: kb-page\n")
    # type appears before created (RENDER_ORDER), tags present (input order), aliases present
    assert block.index("type:") < block.index("created:")
    assert block.index("tags:") < block.index("created:")
    assert "Alt Name" in block


def test_round_trip_parse_render_parse_is_stable():
    fm = {
        "type": "entity",
        "category": "person",
        "review_status": "not_processed",
        "tags": ["x"],
        "aliases": ["Bob"],
        "created": "2026-05-01",
        "updated": "2026-05-01",
        "custom": "kept",
    }
    p1 = parse_frontmatter(fm)
    import yaml

    fm2 = yaml.safe_load(render_block(p1).split("\n", 1)[1])  # drop marker line
    p2 = parse_frontmatter(fm2)
    assert p1 == p2


def test_none_typed_column_round_trips_stably():
    fm = {
        "type": "summary",
        "subtype": None,
        "category": None,
        "created": "2026-05-01",
        "updated": "2026-05-01",
    }
    p1 = parse_frontmatter(fm)
    assert "subtype" not in p1.typed  # None typed values dropped at parse
    assert "category" not in p1.typed
    import yaml

    fm2 = yaml.safe_load(render_block(p1).split("\n", 1)[1])
    assert parse_frontmatter(fm2) == p1
