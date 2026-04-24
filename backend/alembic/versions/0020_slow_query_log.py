"""add slow query log

Revision ID: 0020_slow_query_log
Revises: 0019_session_snapshot
Create Date: 2026-04-24 11:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_slow_query_log"
down_revision = "0019_session_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slow_query_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, comment="platform/mysql_slowlog/pgsql_statements/redis_slowlog"),
        sa.Column("source_ref", sa.String(length=128), nullable=False, comment="来源内去重标识"),
        sa.Column("instance_id", sa.Integer(), nullable=True),
        sa.Column("instance_name", sa.String(length=100), nullable=False, comment="实例名称快照"),
        sa.Column("db_type", sa.String(length=20), nullable=False, comment="数据库类型快照"),
        sa.Column("db_name", sa.String(length=128), nullable=False, comment="数据库/Schema"),
        sa.Column("sql_text", sa.Text(), nullable=False, comment="SQL 文本"),
        sa.Column("sql_fingerprint", sa.String(length=64), nullable=False, comment="SQL 指纹"),
        sa.Column("fingerprint_text", sa.Text(), nullable=False, comment="归一化 SQL"),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, comment="执行耗时(ms)"),
        sa.Column("rows_examined", sa.BigInteger(), nullable=False, comment="扫描行数"),
        sa.Column("rows_sent", sa.BigInteger(), nullable=False, comment="返回行数"),
        sa.Column("username", sa.String(length=128), nullable=False, comment="数据库/平台用户"),
        sa.Column("client_host", sa.String(length=255), nullable=False, comment="客户端主机"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, comment="发生时间"),
        sa.Column("raw", sa.JSON(), nullable=False, comment="原始数据"),
        sa.Column("analysis_tags", sa.JSON(), nullable=False, comment="分析标签"),
        sa.Column("collect_error", sa.Text(), nullable=False, comment="采集错误"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["instance_id"], ["sql_instance.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_ref", name="uq_slowlog_source_ref"),
    )
    op.create_index("ix_slowlog_db_type_time", "slow_query_log", ["db_type", "occurred_at"])
    op.create_index("ix_slowlog_fingerprint", "slow_query_log", ["sql_fingerprint"])
    op.create_index("ix_slowlog_instance_time", "slow_query_log", ["instance_id", "occurred_at"])
    op.create_index("ix_slowlog_source", "slow_query_log", ["source"])
    op.create_index("ix_slowlog_tenant", "slow_query_log", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_slowlog_tenant", table_name="slow_query_log")
    op.drop_index("ix_slowlog_source", table_name="slow_query_log")
    op.drop_index("ix_slowlog_instance_time", table_name="slow_query_log")
    op.drop_index("ix_slowlog_fingerprint", table_name="slow_query_log")
    op.drop_index("ix_slowlog_db_type_time", table_name="slow_query_log")
    op.drop_table("slow_query_log")
