from kb.db import Page, PageAlias, PageSource, PageTag


def test_models_importable_and_tablenames():
    assert Page.__tablename__ == "pages"
    assert PageTag.__tablename__ == "page_tags"
    assert PageSource.__tablename__ == "page_sources"
    assert PageAlias.__tablename__ == "page_aliases"
