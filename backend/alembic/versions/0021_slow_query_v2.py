"""slow query v2 config

Revision ID: 0021_slow_query_v2
Revises: 0020_slow_query_log
Create Date: 2026-04-24 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_slow_query_v2"
down_revision = "0020_slow_query_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slow_query_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False, comment="实例ID"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, comment="是否启用慢日志采集"),
        sa.Column("threshold_ms", sa.Integer(), nullable=False, comment="慢 SQL 阈值(ms)"),
        sa.Column("collect_interval", sa.Integer(), nullable=False, comment="采集间隔(秒)"),
        sa.Column("retention_days", sa.Integer(), nullable=False, comment="保留天数"),
        sa.Column("collect_limit", sa.Integer(), nullable=False, comment="单次采集上限"),
        sa.Column("last_collect_at", sa.DateTime(timezone=True), nullable=True, comment="最近采集时间"),
        sa.Column("last_collect_status", sa.String(length=20), nullable=False, comment="never/success/partial/failed/unsupported"),
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
    op.create_index("ix_slowcfg_enabled", "slow_query_config", ["is_enabled"])
    op.create_index("ix_slowcfg_instance", "slow_query_config", ["instance_id"])
    op.create_index("ix_slowcfg_tenant", "slow_query_config", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_slowcfg_tenant", table_name="slow_query_config")
    op.drop_index("ix_slowcfg_instance", table_name="slow_query_config")
    op.drop_index("ix_slowcfg_enabled", table_name="slow_query_config")
    op.drop_table("slow_query_config")
