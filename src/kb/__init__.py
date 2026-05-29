"""kb — KnowledgeBase lint and reporting CLI tooling."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    """Resolve the data tree root from ``KB_DATA_DIR`` (default ``<repo>/data``).

    Matches ``src/kb/web/config.py`` semantics: the variable is the data
    *root*; ``wiki/``, ``raw/``, ``handoffs/`` are derived as children.
    """
    return Path(os.environ.get("KB_DATA_DIR", str(REPO_ROOT / "data"))).resolve()


__all__ = ["REPO_ROOT", "data_dir"]
