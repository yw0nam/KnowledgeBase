"""Runtime config for kb-web.

`data/` is local-only and excluded from the outer repo, so a worktree
created from the main branch will not have a `data/` directory at all.
The host should point at the real one with `KB_DATA_DIR`; otherwise
the default at `<repo_root>/data` is used and may simply be absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from kb import REPO_ROOT


@dataclass(frozen=True)
class WebConfig:
    data_dir: Path
    host: str
    port: int
    cors_origins: tuple[str, ...]

    @property
    def wiki_dir(self) -> Path:
        return self.data_dir / "wiki"

    @property
    def rejected_dir(self) -> Path:
        return self.data_dir / "rejected"

    @property
    def handoffs_dir(self) -> Path:
        return self.data_dir / "handoffs"


def load() -> WebConfig:
    data_dir = Path(os.environ.get("KB_DATA_DIR", REPO_ROOT / "data")).resolve()
    host = os.environ.get("KB_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("KB_WEB_PORT", "8765"))
    origins_raw = os.environ.get(
        "KB_WEB_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    cors_origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip())
    return WebConfig(
        data_dir=data_dir,
        host=host,
        port=port,
        cors_origins=cors_origins,
    )
