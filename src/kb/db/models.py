"""SQLAlchemy ORM models for the KnowledgeBase state DB.

Schema source of truth lives in Alembic migrations; these models mirror
it for query/repo layers in later tasks.
"""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    origin: Mapped[str] = mapped_column(String, nullable=False, default="ingested")
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    frontmatter: Mapped[dict] = mapped_column(JSON, nullable=False)
    export_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class RawSource(Base):
    __tablename__ = "raw_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    frontmatter: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class PageSource(Base):
    __tablename__ = "page_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False)
    raw_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_sources.id"), nullable=True
    )
    citation_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class PageRevision(Base):
    __tablename__ = "page_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_kind: Mapped[str] = mapped_column(String, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    frontmatter: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="migration")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handoff_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    task_slug: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    handoff_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    frontmatter: Mapped[dict] = mapped_column(JSON, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    export_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    log_date: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class CronRun(Base):
    __tablename__ = "cron_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_body: Mapped[str] = mapped_column(Text, nullable=False)
    log_path: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_at: Mapped[str] = mapped_column(String, nullable=False)


class MetricsRecord(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        UniqueConstraint("report_date", "report_type", name="uq_metrics_date_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[str] = mapped_column(String, nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)
    session_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    tool_error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
