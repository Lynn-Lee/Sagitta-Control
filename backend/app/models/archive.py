"""Archive job models."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ArchiveJobStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELING = "canceling"
    CANCELED = "canceled"
    SUCCESS = "success"
    FAILED = "failed"


class ArchiveBatchStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class ArchiveJob(BaseModel):
    """Long-running archive/cleanup job."""

    __tablename__ = "archive_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sql_workflow.id", ondelete="SET NULL"), nullable=True, comment="审批工单ID"
    )
    celery_task_id: Mapped[str] = mapped_column(String(100), default="", comment="Celery task ID")

    status: Mapped[str] = mapped_column(String(20), default=ArchiveJobStatus.PENDING_REVIEW, nullable=False)
    archive_mode: Mapped[str] = mapped_column(String(20), nullable=False, comment="purge/dest")

    source_instance_id: Mapped[int] = mapped_column(Integer, ForeignKey("sql_instance.id"), nullable=False)
    source_db: Mapped[str] = mapped_column(String(128), nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    condition: Mapped[str] = mapped_column(Text, nullable=False)

    dest_instance_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sql_instance.id"), nullable=True)
    dest_db: Mapped[str] = mapped_column(String(128), default="")
    dest_table: Mapped[str] = mapped_column(String(128), default="")

    batch_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    sleep_ms: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    estimated_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_batch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_is_estimated: Mapped[bool] = mapped_column(default=False, nullable=False)

    apply_reason: Mapped[str] = mapped_column(String(500), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("sql_users.id"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    batches: Mapped[list[ArchiveBatchLog]] = relationship(
        "ArchiveBatchLog", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_archive_job_status", "status"),
        Index("ix_archive_job_workflow", "workflow_id"),
        Index("ix_archive_job_source", "source_instance_id", "source_db", "source_table"),
        Index("ix_archive_job_created_by", "created_by_id"),
        Index("ix_archive_job_tenant", "tenant_id"),
    )


class ArchiveBatchLog(BaseModel):
    """Per-batch execution log for an archive job."""

    __tablename__ = "archive_batch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("archive_job.id", ondelete="CASCADE"), nullable=False)
    batch_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[ArchiveJob] = relationship("ArchiveJob", back_populates="batches")

    __table_args__ = (
        Index("ix_archive_batch_job", "job_id", "batch_no"),
        Index("ix_archive_batch_tenant", "tenant_id"),
    )
