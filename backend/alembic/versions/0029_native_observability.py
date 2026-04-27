"""native observability snapshots

Revision ID: 0029_native_observability
Revises: 0028_archive_execute_perm
Create Date: 2026-04-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0029_native_observability"
down_revision = "0028_archive_execute_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("monitor_collect_config", "exporter_url", existing_type=sa.String(length=500), nullable=True)
    op.alter_column("monitor_collect_config", "exporter_type", existing_type=sa.String(length=50), nullable=True)
    op.add_column("monitor_collect_config", sa.Column("capacity_collect_interval", sa.Integer(), nullable=False, server_default="3600", comment="容量采集间隔(秒)"))
    op.add_column("monitor_collect_config", sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30", comment="指标保留天数"))
    op.add_column("monitor_collect_config", sa.Column("last_metric_collect_at", sa.DateTime(timezone=True), nullable=True, comment="最近实例指标采集时间"))
    op.add_column("monitor_collect_config", sa.Column("last_capacity_collect_at", sa.DateTime(timezone=True), nullable=True, comment="最近容量采集时间"))
    op.add_column("monitor_collect_config", sa.Column("last_collect_status", sa.String(length=30), nullable=False, server_default="pending", comment="最近采集状态"))
    op.add_column("monitor_collect_config", sa.Column("last_collect_error", sa.Text(), nullable=False, server_default="", comment="最近采集错误"))

    op.create_table(
        "monitor_metric_snapshot",
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("missing_groups", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("uptime_seconds", sa.BigInteger(), nullable=True),
        sa.Column("current_connections", sa.Integer(), nullable=True),
        sa.Column("active_sessions", sa.Integer(), nullable=True),
        sa.Column("max_connections", sa.Integer(), nullable=True),
        sa.Column("connection_usage", sa.Float(), nullable=True),
        sa.Column("qps", sa.Float(), nullable=True),
        sa.Column("tps", sa.Float(), nullable=True),
        sa.Column("slow_queries", sa.BigInteger(), nullable=True),
        sa.Column("error_count", sa.BigInteger(), nullable=True),
        sa.Column("lock_waits", sa.Integer(), nullable=True),
        sa.Column("long_transactions", sa.Integer(), nullable=True),
        sa.Column("replication_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("extra_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_mms_instance_time", "monitor_metric_snapshot", ["instance_id", "collected_at"])
    op.create_index("ix_mms_tenant", "monitor_metric_snapshot", ["tenant_id"])

    op.create_table(
        "monitor_database_capacity_snapshot",
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("db_name", sa.String(length=128), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("index_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="success"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_mdcs_instance_time", "monitor_database_capacity_snapshot", ["instance_id", "collected_at"])
    op.create_index("ix_mdcs_db", "monitor_database_capacity_snapshot", ["instance_id", "db_name"])
    op.create_index("ix_mdcs_tenant", "monitor_database_capacity_snapshot", ["tenant_id"])

    op.create_table(
        "monitor_table_capacity_snapshot",
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("db_name", sa.String(length=128), nullable=False),
        sa.Column("table_name", sa.String(length=256), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("index_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_mtcs_instance_time", "monitor_table_capacity_snapshot", ["instance_id", "collected_at"])
    op.create_index("ix_mtcs_table", "monitor_table_capacity_snapshot", ["instance_id", "db_name", "table_name"])
    op.create_index("ix_mtcs_total_size", "monitor_table_capacity_snapshot", ["instance_id", "total_size_bytes"])
    op.create_index("ix_mtcs_tenant", "monitor_table_capacity_snapshot", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_mtcs_tenant", table_name="monitor_table_capacity_snapshot")
    op.drop_index("ix_mtcs_total_size", table_name="monitor_table_capacity_snapshot")
    op.drop_index("ix_mtcs_table", table_name="monitor_table_capacity_snapshot")
    op.drop_index("ix_mtcs_instance_time", table_name="monitor_table_capacity_snapshot")
    op.drop_table("monitor_table_capacity_snapshot")

    op.drop_index("ix_mdcs_tenant", table_name="monitor_database_capacity_snapshot")
    op.drop_index("ix_mdcs_db", table_name="monitor_database_capacity_snapshot")
    op.drop_index("ix_mdcs_instance_time", table_name="monitor_database_capacity_snapshot")
    op.drop_table("monitor_database_capacity_snapshot")

    op.drop_index("ix_mms_tenant", table_name="monitor_metric_snapshot")
    op.drop_index("ix_mms_instance_time", table_name="monitor_metric_snapshot")
    op.drop_table("monitor_metric_snapshot")

    op.drop_column("monitor_collect_config", "last_collect_error")
    op.drop_column("monitor_collect_config", "last_collect_status")
    op.drop_column("monitor_collect_config", "last_capacity_collect_at")
    op.drop_column("monitor_collect_config", "last_metric_collect_at")
    op.drop_column("monitor_collect_config", "retention_days")
    op.drop_column("monitor_collect_config", "capacity_collect_interval")
    op.alter_column("monitor_collect_config", "exporter_type", existing_type=sa.String(length=50), nullable=False)
    op.alter_column("monitor_collect_config", "exporter_url", existing_type=sa.String(length=500), nullable=False)
