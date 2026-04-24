"""session collect config

Revision ID: 0022_session_collect_config
Revises: 0021_slow_query_v2
Create Date: 2026-04-24 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_session_collect_config"
down_revision = "0021_slow_query_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_collect_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False, comment="实例ID"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, comment="是否启用会话采集"),
        sa.Column("collect_interval", sa.Integer(), nullable=False, comment="采集间隔(秒)"),
        sa.Column("retention_days", sa.Integer(), nullable=False, comment="保留天数"),
        sa.Column("last_collect_at", sa.DateTime(timezone=True), nullable=True, comment="最近采集时间"),
        sa.Column("last_collect_status", sa.String(length=20), nullable=False, comment="never/success/failed/skipped"),
        sa.Column("last_collect_error", sa.Text(), nullable=False, comment="最近采集错误"),
        sa.Column("last_collect_count", sa.Integer(), nullable=False, comment="最近新增条数"),
        sa.Column("created_by", sa.String(length=100), nullable=False, comment="创建人"),
        sa.Column("tenant_id", sa.Integer(), nullable=False, comment="租户ID（SaaS预留）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["instance_id"], ["sql_instance.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id"),
    )
    op.create_index("ix_sessioncfg_enabled", "session_collect_config", ["is_enabled"])
    op.create_index("ix_sessioncfg_instance", "session_collect_config", ["instance_id"])
    op.create_index("ix_sessioncfg_tenant", "session_collect_config", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_sessioncfg_tenant", table_name="session_collect_config")
    op.drop_index("ix_sessioncfg_instance", table_name="session_collect_config")
    op.drop_index("ix_sessioncfg_enabled", table_name="session_collect_config")
    op.drop_table("session_collect_config")
