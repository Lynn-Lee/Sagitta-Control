"""extend query log for query history audit

Revision ID: 0017_query_log_history_audit
Revises: 0016_workflow_execution_decision
Create Date: 2026-04-23 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_query_log_history_audit"
down_revision = "0016_workflow_execution_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "query_log",
        sa.Column("operation_type", sa.String(length=20), nullable=False, server_default="execute", comment="操作类型：execute/export"),
    )
    op.add_column(
        "query_log",
        sa.Column("export_format", sa.String(length=10), nullable=False, server_default="", comment="导出格式"),
    )
    op.add_column(
        "query_log",
        sa.Column("username", sa.String(length=100), nullable=False, server_default="", comment="操作人快照"),
    )
    op.add_column(
        "query_log",
        sa.Column("instance_name", sa.String(length=100), nullable=False, server_default="", comment="实例名称快照"),
    )
    op.add_column(
        "query_log",
        sa.Column("db_type", sa.String(length=20), nullable=False, server_default="", comment="数据库类型快照"),
    )
    op.add_column(
        "query_log",
        sa.Column("client_ip", sa.String(length=50), nullable=False, server_default="", comment="客户端IP"),
    )
    op.add_column(
        "query_log",
        sa.Column("error", sa.Text(), nullable=False, server_default="", comment="失败原因"),
    )
    op.create_index("ix_qlog_operation_type", "query_log", ["operation_type"])
    for column in ["operation_type", "export_format", "username", "instance_name", "db_type", "client_ip", "error"]:
        op.alter_column("query_log", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_qlog_operation_type", table_name="query_log")
    op.drop_column("query_log", "error")
    op.drop_column("query_log", "client_ip")
    op.drop_column("query_log", "db_type")
    op.drop_column("query_log", "instance_name")
    op.drop_column("query_log", "username")
    op.drop_column("query_log", "export_format")
    op.drop_column("query_log", "operation_type")
