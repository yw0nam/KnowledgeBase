"""Hermes kanban CLI bridges.

Pure helpers consumed by ``kb.web.routes.kanban`` and
``kb.web.routes.dispatches``. Subprocess shells out to
``hermes kanban`` and parses JSON; no FastAPI awareness lives here.
The route layer is responsible for translating these exceptions into
HTTP responses.

Deviations from spec:
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
import subprocess
from dataclasses import dataclass

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
    """Archive a previously created card.

    Used by the dispatch cancel route's two-state machine. Output is
    plaintext ("Archived <id>"); we don't parse it. Any non-zero exit
    propagates as ``HermesRejected``.
    """
    _run_hermes(["kanban", "archive", task_id])
