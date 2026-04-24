"""add session snapshot history

Revision ID: 0019_session_snapshot
Revises: 0018_qlog_snapshot_backfill
Create Date: 2026-04-24 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_session_snapshot"
down_revision = "0018_qlog_snapshot_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, comment="采集时间"),
        sa.Column("instance_id", sa.Integer(), nullable=True),
        sa.Column("instance_name", sa.String(length=100), nullable=False, comment="实例名称快照"),
        sa.Column("db_type", sa.String(length=20), nullable=False, comment="数据库类型快照"),
        sa.Column("session_id", sa.String(length=128), nullable=False, comment="会话ID"),
        sa.Column("serial", sa.String(length=128), nullable=False, comment="Oracle SERIAL# 等二级标识"),
        sa.Column("username", sa.String(length=128), nullable=False, comment="数据库用户"),
        sa.Column("host", sa.String(length=255), nullable=False, comment="客户端主机"),
        sa.Column("program", sa.String(length=255), nullable=False, comment="客户端程序"),
        sa.Column("db_name", sa.String(length=128), nullable=False, comment="数据库/Schema"),
        sa.Column("command", sa.String(length=128), nullable=False, comment="命令类型"),
        sa.Column("state", sa.String(length=255), nullable=False, comment="会话状态"),
        sa.Column("time_seconds", sa.Integer(), nullable=False, comment="运行秒数"),
        sa.Column("sql_id", sa.String(length=64), nullable=False, comment="SQL ID"),
        sa.Column("sql_text", sa.Text(), nullable=False, comment="SQL 文本"),
        sa.Column("event", sa.String(length=255), nullable=False, comment="等待事件"),
        sa.Column("blocking_session", sa.String(length=128), nullable=False, comment="阻塞会话"),
        sa.Column("source", sa.String(length=32), nullable=False, comment="采集来源"),
        sa.Column("collect_error", sa.Text(), nullable=False, comment="采集错误"),
        sa.Column("raw", sa.JSON(), nullable=False, comment="原始会话行"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["instance_id"], ["sql_instance.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_snapshot_collected_at", "session_snapshot", ["collected_at"])
    op.create_index("ix_session_snapshot_db_type_time", "session_snapshot", ["db_type", "collected_at"])
    op.create_index("ix_session_snapshot_inst_time", "session_snapshot", ["instance_id", "collected_at"])
    op.create_index("ix_session_snapshot_session", "session_snapshot", ["session_id", "serial"])
    op.create_index("ix_session_snapshot_tenant", "session_snapshot", ["tenant_id"])
    op.create_index("ix_session_snapshot_user", "session_snapshot", ["username"])


def downgrade() -> None:
    op.drop_index("ix_session_snapshot_user", table_name="session_snapshot")
    op.drop_index("ix_session_snapshot_tenant", table_name="session_snapshot")
    op.drop_index("ix_session_snapshot_session", table_name="session_snapshot")
    op.drop_index("ix_session_snapshot_inst_time", table_name="session_snapshot")
    op.drop_index("ix_session_snapshot_db_type_time", table_name="session_snapshot")
    op.drop_index("ix_session_snapshot_collected_at", table_name="session_snapshot")
    op.drop_table("session_snapshot")
