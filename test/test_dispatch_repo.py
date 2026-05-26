"""Tests for ``kb.db.repos.dispatch_repo``.

Covers the five repo-level behaviours that protect the wire contract:

- Idempotency-Key replay returns the existing row unchanged.
- ``update_status`` enforces a monotonic ``occurred_at`` ratchet.
- ``update_status`` enforces the documented transition graph.
- ``cancel_phase_one`` → ``cancel_phase_two`` walks dispatched →
  cancelling → cancelled.
- UNIQUE(external_board_id, external_task_id) violation surfaces as
  ``sqlalchemy.exc.IntegrityError`` on a fresh (non-replay) insert.

Each test uses a real on-disk SQLite DB created by running the head
Alembic migration so CHECK constraints, triggers, and partial unique
indexes all fire as they will in production.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.fixture()
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    command.upgrade(_alembic_cfg(), "head")
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _create(session: Session, **overrides):
    from kb.db.repos import dispatch_repo

    defaults = dict(
        page_stem="Foo",
        page_path_at_dispatch="wiki/improvements/2026-05/Foo.md",
        external_board_id="kb-main",
        external_task_id="t_abc",
        direction=None,
        idempotency_key=None,
        created_at="2026-05-26T10:00:00+09:00",
        dispatched_at="2026-05-26T10:00:00+09:00",
    )
    defaults.update(overrides)
    return dispatch_repo.create_dispatch(session, **defaults)


def test_create_with_idempotency_key_replay_returns_existing_row(
    session: Session,
) -> None:
    first = _create(
        session,
        idempotency_key="key-1",
        external_task_id="t_first",
    )

    replay = _create(
        session,
        idempotency_key="key-1",
        # Different external_task_id would normally collide with first's
        # row by board_id/task_id; the replay must short-circuit and
        # return the existing row unchanged.
        external_task_id="t_replay_should_not_insert",
    )

    assert replay.id == first.id
    assert replay.external_task_id == "t_first"
    assert replay.idempotency_key == "key-1"


def test_update_status_monotonic_occurred_at_violation_raises_status_out_of_order(
    session: Session,
) -> None:
    from kb.db.repos import dispatch_repo

    row = _create(session)

    # First push moves us to in_progress and stamps last_status_at.
    dispatch_repo.update_status(
        session,
        dispatch_id=row.id,
        new_status="in_progress",
        occurred_at="2026-05-26T11:00:00+09:00",
        result_payload=None,
        server_now="2026-05-26T11:00:01+09:00",
    )

    # A later push reporting an earlier occurred_at must be rejected.
    with pytest.raises(dispatch_repo.StatusOutOfOrder):
        dispatch_repo.update_status(
            session,
            dispatch_id=row.id,
            new_status="done",
            occurred_at="2026-05-26T10:59:59+09:00",
            result_payload=None,
            server_now="2026-05-26T11:01:00+09:00",
        )


def test_update_status_transition_graph_violation_raises_transition_violation(
    session: Session,
) -> None:
    from kb.db.repos import dispatch_repo

    row = _create(session)

    dispatch_repo.update_status(
        session,
        dispatch_id=row.id,
        new_status="done",
        occurred_at=None,
        result_payload=None,
        server_now="2026-05-26T11:00:00+09:00",
    )

    # done is terminal: any further transition must raise.
    with pytest.raises(dispatch_repo.TransitionViolation):
        dispatch_repo.update_status(
            session,
            dispatch_id=row.id,
            new_status="in_progress",
            occurred_at=None,
            result_payload=None,
            server_now="2026-05-26T11:01:00+09:00",
        )


def test_cancel_state_machine_dispatched_to_cancelling_to_cancelled(
    session: Session,
) -> None:
    from kb.db.repos import dispatch_repo

    row = _create(session)

    phase1 = dispatch_repo.cancel_phase_one(
        session,
        dispatch_id=row.id,
        server_now="2026-05-26T11:00:00+09:00",
    )
    assert phase1.status == "cancelling"
    assert phase1.last_status_at == "2026-05-26T11:00:00+09:00"

    phase2 = dispatch_repo.cancel_phase_two(
        session,
        dispatch_id=row.id,
        server_now="2026-05-26T11:00:05+09:00",
    )
    assert phase2.status == "cancelled"
    assert phase2.last_status_at == "2026-05-26T11:00:05+09:00"


def test_unique_external_board_external_task_violation_raises_integrity_error(
    session: Session,
) -> None:
    _create(session, external_board_id="kb-main", external_task_id="t_dup")
    with pytest.raises(IntegrityError):
        _create(session, external_board_id="kb-main", external_task_id="t_dup")
