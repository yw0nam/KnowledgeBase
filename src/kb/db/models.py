"""SQLAlchemy ORM models for the operational state DB.

Schema source of truth lives in the initial Alembic migration; these
models mirror it for query/repo layers in later tasks.
"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Dispatch(Base):
    __tablename__ = "dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_stem: Mapped[str] = mapped_column(String, nullable=False)
    page_path_at_dispatch: Mapped[str] = mapped_column(String, nullable=False)
    external_board_id: Mapped[str] = mapped_column(String, nullable=False)
    external_task_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="dispatched")
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    dispatched_at: Mapped[str] = mapped_column(String, nullable=False)
    last_status_at: Mapped[str | None] = mapped_column(String, nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class WikiEdit(Base):
    __tablename__ = "wiki_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_stem: Mapped[str] = mapped_column(String, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    edited_at: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="console")
