"""Hermes kanban CLI bridges + improvement-page dispatch frontmatter edit.

Pure helpers consumed by ``kb.web.routes.kanban``. Subprocess shells
out to ``hermes kanban`` and parses JSON; no FastAPI awareness lives
here. The route layer is responsible for translating these exceptions
into HTTP responses.

Deviations from spec §6.2:
- ``hermes kanban create`` does not accept ``--metadata``. The metadata
  pair is embedded in the card body as a trailing
  ``<!-- kb-meta: {...} -->`` line (Appendix A item 2 fallback).
- Hermes returns the created task id under the field ``id``. We
  normalize to ``task_id`` at this boundary so the rest of the system
  matches the spec's contract.
- ``counts`` is treated as a sparse ``dict[str, int]`` — Hermes omits
  zero buckets — rather than the fixed five-key shape sketched in §7.1.
  The route surfaces what we receive; the frontend can default missing
  keys to zero if it cares to.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from kb.cli.wiki_review._store import _split_frontmatter

# Subprocess timeout for hermes calls (seconds). Hermes is local; if it
# hasn't responded in 10s the daemon is effectively unavailable.
HERMES_TIMEOUT = 10


class HermesUnavailable(Exception):
    """Hermes CLI is missing, the daemon is down, or it timed out."""


class HermesRejected(Exception):
    """Hermes returned a non-zero exit with a parseable error message."""


class BoardNotFound(Exception):
    """The requested board_slug is not present in the current boards list."""


@dataclass(frozen=True)
class Board:
    slug: str
    name: str
    counts: dict[str, int]


@dataclass(frozen=True)
class Card:
    task_id: str
    board: str


def _run_hermes(args: list[str]) -> str:
    """Run ``hermes <args>`` and return stdout.

    Maps subprocess failure modes onto the two hermes-facing exceptions:
    missing binary or timeout → ``HermesUnavailable``; non-zero exit →
    ``HermesRejected`` carrying stderr (falling back to stdout when
    stderr is empty, since some hermes errors print to stdout).
    """
    try:
        result = subprocess.run(
            ["hermes", *args],
            capture_output=True,
            text=True,
            timeout=HERMES_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise HermesUnavailable("hermes CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise HermesUnavailable(f"hermes timed out after {HERMES_TIMEOUT}s") from exc

    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        raise HermesRejected(msg or f"hermes exited {result.returncode}")
    return result.stdout


def list_boards() -> list[Board]:
    """Return the current Hermes kanban boards.

    ``counts`` is passed through as-is — Hermes emits a sparse object
    that omits zero buckets. Callers must treat it as ``dict[str, int]``.
    """
    raw = _run_hermes(["kanban", "boards", "list", "--json"])
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HermesRejected(f"hermes returned non-JSON output: {exc}") from exc
    if not isinstance(payload, list):
        raise HermesRejected("expected JSON array from `hermes kanban boards list`")

    boards: list[Board] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        name = item.get("name")
        counts = item.get("counts") or {}
        if not isinstance(slug, str) or not isinstance(name, str):
            continue
        if not isinstance(counts, dict):
            counts = {}
        boards.append(Board(slug=slug, name=name, counts=dict(counts)))
    return boards


def create_card(board_slug: str, title: str, body: str) -> Card:
    """Create a card on the given board.

    The metadata pair documented in §6.4 is appended as a comment line
    to ``body`` by the caller (see ``routes/kanban.py``); this helper
    does not synthesise it.
    """
    # `--board` belongs on the `kanban` parent subcommand, not on `create`.
    # `hermes kanban --board <slug> create ...` is the correct form.
    raw = _run_hermes(
        [
            "kanban",
            "--board",
            board_slug,
            "create",
            "--body",
            body,
            "--json",
            title,
        ]
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HermesRejected(f"hermes returned non-JSON output: {exc}") from exc
    if not isinstance(payload, dict):
        raise HermesRejected("expected JSON object from `hermes kanban create`")

    # Hermes uses `id`; normalize to `task_id` at this boundary.
    task_id = payload.get("id") or payload.get("task_id")
    board = payload.get("board") or board_slug
    if not isinstance(task_id, str) or not task_id:
        raise HermesRejected("hermes response missing `id` field")
    if not isinstance(board, str):
        board = board_slug
    return Card(task_id=task_id, board=board)


def archive_card(task_id: str) -> None:
    """Archive a previously created card (used as rollback).

    Output is plaintext ("Archived <id>"); we don't parse it. Any
    non-zero exit propagates as ``HermesRejected`` so the route can
    distinguish "rollback succeeded" from "rollback failed".
    """
    _run_hermes(["kanban", "archive", task_id])


def append_dispatch(page_path: Path, dispatch_entry: dict) -> None:
    """Append ``dispatch_entry`` to the page's ``kanban_dispatches`` list.

    Reads the page, splits frontmatter, parses the YAML block, appends
    the entry to the list (creating it if missing), then re-serialises
    YAML and writes atomically via a same-directory temp file +
    ``os.replace``. Body bytes are preserved verbatim, including the
    final newline state.

    YAML re-serialisation here is intentional — the new entry is a
    multi-key mapping inside a list, so the targeted regex helpers in
    ``_store`` can't express it cleanly. Other frontmatter keys round-
    trip through ``yaml.safe_load`` / ``yaml.safe_dump`` and retain
    their values (though not necessarily exact spacing/quoting).
    """
    text = page_path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{page_path}: missing or malformed frontmatter")
    fm_block, body = parts

    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{page_path}: malformed YAML frontmatter") from exc
    if not isinstance(fm, dict):
        raise ValueError(f"{page_path}: frontmatter is not a mapping")

    dispatches = fm.get("kanban_dispatches")
    if not isinstance(dispatches, list):
        dispatches = []
    dispatches.append(dispatch_entry)
    fm["kanban_dispatches"] = dispatches

    new_fm_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )

    new_text = f"---\n{new_fm_block}---{body}"

    # Atomic write: write to temp in same dir, then os.replace.
    parent = page_path.parent
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{page_path.name}.", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(new_text)
        os.replace(tmp_path, page_path)
    except Exception:
        # Clean up the temp file on any failure before re-raising.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
