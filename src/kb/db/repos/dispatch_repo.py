"""CRUD helpers for the ``dispatches`` table.

Function-style — the route layer composes these directly. Exceptions
raised here map to HTTP status codes in ``kb.web.routes.dispatches``;
keeping the mapping out of this module lets CLI callers (e.g. the
backfill) use the same helpers without depending on FastAPI.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kb.db.models import Dispatch


class DispatchNotFound(Exception):
    """No row with the given id exists."""


class TransitionViolation(Exception):
    """The requested status transition is not allowed by the graph."""


class StatusOutOfOrder(Exception):
    """``occurred_at`` is ``<= last_status_at`` for an existing row."""


# Source of truth for §6.3's transition graph. Terminal states map to
# an empty frozenset so a single ``in <allowed>`` check covers both
# "not allowed" and "row is terminal".
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "dispatched": frozenset({"in_progress", "done", "failed", "cancelling"}),
    "in_progress": frozenset({"done", "failed", "cancelling"}),
    "cancelling": frozenset({"cancelled"}),
    "done": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

_NON_TERMINAL: frozenset[str] = frozenset(
    {s for s, allowed in _ALLOWED_TRANSITIONS.items() if allowed}
)

_CANCEL_PHASE_ONE_FROM: frozenset[str] = frozenset({"dispatched", "in_progress"})


def create_dispatch(
    session: Session,
    *,
    page_stem: str,
    page_path_at_dispatch: str,
    external_board_id: str,
    external_task_id: str,
    direction: str | None,
    idempotency_key: str | None,
    created_at: str,
    dispatched_at: str,
) -> Dispatch:
    """Insert a dispatched row, or replay an Idempotency-Key match.

    ``idempotency_key`` is the contract: a non-None key that matches an
    existing row short-circuits and returns that row unchanged (HTTP
    200 replay semantics). A fresh insert that collides on
    ``UNIQUE(external_board_id, external_task_id)`` propagates as
    ``sqlalchemy.exc.IntegrityError`` for the caller to translate.
    """
    if idempotency_key is not None:
        existing = session.execute(
            select(Dispatch).where(Dispatch.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    row = Dispatch(
        page_stem=page_stem,
        page_path_at_dispatch=page_path_at_dispatch,
        external_board_id=external_board_id,
        external_task_id=external_task_id,
        direction=direction,
        status="dispatched",
        idempotency_key=idempotency_key,
        created_at=created_at,
        dispatched_at=dispatched_at,
        last_status_at=None,
        result_payload=None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _load(session: Session, dispatch_id: int) -> Dispatch:
    row = session.get(Dispatch, dispatch_id)
    if row is None:
        raise DispatchNotFound(f"dispatch id={dispatch_id} not found")
    return row


def _check_transition(current: str, new: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise TransitionViolation(f"transition not allowed: {current} -> {new}")


def update_status(
    session: Session,
    *,
    dispatch_id: int,
    new_status: str,
    occurred_at: str | None,
    result_payload: dict | None,
    server_now: str,
) -> Dispatch:
    """Apply a status push from a worker (or the cancel route).

    ``server_now`` is always stamped onto ``last_status_at`` regardless
    of ``occurred_at``; ``occurred_at`` only feeds the monotonic check
    (catches retry reordering on the wire).
    """
    row = _load(session, dispatch_id)
    _check_transition(row.status, new_status)

    if (
        occurred_at is not None
        and row.last_status_at is not None
        and occurred_at <= row.last_status_at
    ):
        raise StatusOutOfOrder(
            f"occurred_at={occurred_at} <= last_status_at={row.last_status_at}"
        )

    row.status = new_status
    row.last_status_at = server_now
    if result_payload is not None:
        row.result_payload = result_payload
    session.commit()
    session.refresh(row)
    return row


def cancel_phase_one(
    session: Session,
    *,
    dispatch_id: int,
    server_now: str,
) -> Dispatch:
    """Flip ``dispatched``/``in_progress`` to ``cancelling``."""
    row = _load(session, dispatch_id)
    if row.status not in _CANCEL_PHASE_ONE_FROM:
        raise TransitionViolation(f"transition not allowed: {row.status} -> cancelling")
    row.status = "cancelling"
    row.last_status_at = server_now
    session.commit()
    session.refresh(row)
    return row


def cancel_phase_two(
    session: Session,
    *,
    dispatch_id: int,
    server_now: str,
) -> Dispatch:
    """Flip ``cancelling`` to ``cancelled`` after a successful archive."""
    row = _load(session, dispatch_id)
    if row.status != "cancelling":
        raise TransitionViolation(f"transition not allowed: {row.status} -> cancelled")
    row.status = "cancelled"
    row.last_status_at = server_now
    session.commit()
    session.refresh(row)
    return row


def force_cancel(
    session: Session,
    *,
    dispatch_id: int,
    server_now: str,
) -> Dispatch:
    """Drop any non-terminal row to ``cancelled`` without calling Hermes."""
    row = _load(session, dispatch_id)
    if row.status not in _NON_TERMINAL:
        raise TransitionViolation(f"transition not allowed: {row.status} -> cancelled")
    row.status = "cancelled"
    row.last_status_at = server_now
    session.commit()
    session.refresh(row)
    return row


def list_dispatches(
    session: Session,
    *,
    page_stem: str | None = None,
    status: str | Iterable[str] | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> tuple[Sequence[Dispatch], int]:
    """Cursor-paginated listing keyed on ``dispatched_at DESC``.

    ``status`` accepts a single string or an iterable; an empty
    iterable is treated as "no filter" (consistent with absent
    multi-valued query params).
    """
    capped = 50 if limit is None else max(1, min(int(limit), 200))

    base = select(Dispatch)
    count_base = select(func.count(Dispatch.id))

    if page_stem is not None:
        base = base.where(Dispatch.page_stem == page_stem)
        count_base = count_base.where(Dispatch.page_stem == page_stem)
    if status is not None:
        if isinstance(status, str):
            statuses = [status]
        else:
            statuses = list(status)
        if statuses:
            base = base.where(Dispatch.status.in_(statuses))
            count_base = count_base.where(Dispatch.status.in_(statuses))

    total = int(session.execute(count_base).scalar_one())

    if since is not None:
        base = base.where(Dispatch.dispatched_at < since)

    base = base.order_by(Dispatch.dispatched_at.desc(), Dispatch.id.desc()).limit(
        capped
    )
    rows = list(session.execute(base).scalars().all())
    return rows, total
