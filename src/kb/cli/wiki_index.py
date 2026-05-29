#!/usr/bin/env python3
"""CLI: ``kb-wiki-index`` — generate or refresh ``data/wiki/INDEX.md``.

Usage:
    uv run kb-wiki-index
"""

from __future__ import annotations

import sys

from kb import data_dir
from kb.cli.wiki.index import INDEX_FILENAME, build_index


def main() -> None:
    wiki_dir = data_dir() / "wiki"
    if not wiki_dir.exists():
        print(f"ERROR: {wiki_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    content = build_index(wiki_dir)
    out_path = wiki_dir / INDEX_FILENAME
    if out_path.exists() and out_path.read_text() == content:
        print(f"INDEX.md already in sync ({out_path})")
        return
    out_path.write_text(content)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
