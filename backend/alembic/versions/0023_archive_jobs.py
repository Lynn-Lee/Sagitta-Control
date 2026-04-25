"""archive jobs

Revision ID: 0023_archive_jobs
Revises: 0022_session_collect_config
Create Date: 2026-04-24 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_archive_jobs"
down_revision = "0022_session_collect_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archive_job",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=True, comment="审批工单ID"),
        sa.Column("celery_task_id", sa.String(length=100), nullable=False, server_default="", comment="Celery task ID"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_review"),
        sa.Column("archive_mode", sa.String(length=20), nullable=False, comment="purge/dest"),
        sa.Column("source_instance_id", sa.Integer(), nullable=False),
        sa.Column("source_db", sa.String(length=128), nullable=False),
        sa.Column("source_table", sa.String(length=128), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("dest_instance_id", sa.Integer(), nullable=True),
        sa.Column("dest_db", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("dest_table", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("sleep_ms", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("estimated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_batch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count_is_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("apply_reason", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["created_by_id"], ["sql_users.id"]),
        sa.ForeignKeyConstraint(["dest_instance_id"], ["sql_instance.id"]),
        sa.ForeignKeyConstraint(["source_instance_id"], ["sql_instance.id"]),
        sa.ForeignKeyConstraint(["workflow_id"], ["sql_workflow.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_archive_job_created_by", "archive_job", ["created_by_id"])
    op.create_index("ix_archive_job_source", "archive_job", ["source_instance_id", "source_db", "source_table"])
    op.create_index("ix_archive_job_status", "archive_job", ["status"])
    op.create_index("ix_archive_job_tenant", "archive_job", ["tenant_id"])
    op.create_index("ix_archive_job_workflow", "archive_job", ["workflow_id"])

    op.create_table(
        "archive_batch_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("selected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["job_id"], ["archive_job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_archive_batch_job", "archive_batch_log", ["job_id", "batch_no"])
    op.create_index("ix_archive_batch_tenant", "archive_batch_log", ["tenant_id"])
    op.execute(
        """
        UPDATE workflow_template
        SET description = '用于小范围、一次性的临时 SQL 删除；大批量历史清理请优先使用数据归档。',
            scene_desc = '适用于少量异常数据或一次性人工 SQL 清理。定期清理、分批限速、跨库迁移等场景请使用数据归档。',
            risk_hint = '删除类操作不可逆，必须先补全校验 SQL 并确认影响行数；大表按条件历史清理建议改走数据归档审批作业。'
        WHERE template_name = '数据清理-按条件删除历史数据'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_archive_batch_tenant", table_name="archive_batch_log")
    op.drop_index("ix_archive_batch_job", table_name="archive_batch_log")
    op.drop_table("archive_batch_log")
    op.drop_index("ix_archive_job_workflow", table_name="archive_job")
    op.drop_index("ix_archive_job_tenant", table_name="archive_job")
    op.drop_index("ix_archive_job_status", table_name="archive_job")
    op.drop_index("ix_archive_job_source", table_name="archive_job")
    op.drop_index("ix_archive_job_created_by", table_name="archive_job")
    op.drop_table("archive_job")
