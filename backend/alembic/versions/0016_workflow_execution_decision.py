"""add workflow execution decision fields

Revision ID: 0016_workflow_execution_decision
Revises: 0015_priv_revoke_backfill
Create Date: 2026-04-21 16:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_workflow_execution_decision"
down_revision = "0015_priv_revoke_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sql_workflow",
        sa.Column("execute_mode", sa.String(length=20), nullable=True, comment="执行方式：immediate/scheduled/external"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("scheduled_execute_at", sa.DateTime(timezone=True), nullable=True, comment="预约平台执行时间"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("executed_by_id", sa.Integer(), nullable=True, comment="执行决策人ID"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("executed_by_name", sa.String(length=100), nullable=True, comment="执行决策人名称"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("external_executed_at", sa.DateTime(timezone=True), nullable=True, comment="外部实际执行时间"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("external_result_status", sa.String(length=20), nullable=True, comment="外部执行结果：success/failed"),
    )
    op.add_column(
        "sql_workflow",
        sa.Column("external_result_remark", sa.String(length=500), nullable=True, comment="外部执行结果备注"),
    )
    op.create_index("ix_workflow_scheduled_execute", "sql_workflow", ["status", "scheduled_execute_at"])
    op.create_foreign_key(
        "fk_sql_workflow_executed_by",
        "sql_workflow",
        "sql_users",
        ["executed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sql_workflow_executed_by", "sql_workflow", type_="foreignkey")
    op.drop_index("ix_workflow_scheduled_execute", table_name="sql_workflow")
    op.drop_column("sql_workflow", "external_result_remark")
    op.drop_column("sql_workflow", "external_result_status")
    op.drop_column("sql_workflow", "external_executed_at")
    op.drop_column("sql_workflow", "executed_by_name")
    op.drop_column("sql_workflow", "executed_by_id")
    op.drop_column("sql_workflow", "scheduled_execute_at")
    op.drop_column("sql_workflow", "execute_mode")
