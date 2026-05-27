from kb.cli.page._fields import (
    JOIN_FIELDS,
    TYPED_COLUMNS,
    RENDER_ORDER,
)


def test_typed_columns_and_join_fields_disjoint():
    assert set(TYPED_COLUMNS).isdisjoint(set(JOIN_FIELDS))


def test_render_order_covers_typed_and_join():
    for k in TYPED_COLUMNS:
        assert k in RENDER_ORDER
    for k in JOIN_FIELDS:
        assert k in RENDER_ORDER
    # 'stem' is identity (filename), never a rendered frontmatter key
    assert "stem" not in RENDER_ORDER
