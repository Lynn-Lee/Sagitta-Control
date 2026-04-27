"""
可观测中心模型（3 张新增表）。
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MonitorCollectConfig(BaseModel):
    """
    监控采集配置。
    每个实例对应一条记录，存储 Exporter 地址和采集参数。
    平台通过 /internal/prometheus/sd-targets 端点将此表数据暴露给 Prometheus HTTP SD。
    """
    __tablename__ = "monitor_collect_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sql_instance.id", ondelete="CASCADE"),
        unique=True,  # 每个实例只有一条采集配置
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用采集")
    # 采集间隔（秒），透传给 Prometheus __scrape_interval__ 标签
    collect_interval: Mapped[int] = mapped_column(Integer, default=60, comment="采集间隔(秒)")
    # 官方 Exporter 地址，如 http://db-host:9104/metrics
    exporter_url: Mapped[str] = mapped_column(
        String(500), default="", comment="Exporter 地址(历史字段，可选)"
    )
    # Exporter 类型（用于前端展示和 Dashboard 路由）
    # mysqld_exporter / postgres_exporter / redis_exporter / ...
    exporter_type: Mapped[str] = mapped_column(
        String(50), default="", comment="Exporter 类型(历史字段，可选)"
    )
    # 实例级告警阈值覆盖（JSON），不填则使用全局默认规则
    alert_rules_override: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="告警阈值覆盖(JSON)"
    )
    created_by: Mapped[str] = mapped_column(String(30), default="", comment="创建人")
    capacity_collect_interval: Mapped[int] = mapped_column(
        Integer, default=3600, comment="容量采集间隔(秒)"
    )
    retention_days: Mapped[int] = mapped_column(Integer, default=30, comment="指标保留天数")
    last_metric_collect_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近实例指标采集时间"
    )
    last_capacity_collect_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近容量采集时间"
    )
    last_collect_status: Mapped[str] = mapped_column(String(30), default="pending", comment="最近采集状态")
    last_collect_error: Mapped[str] = mapped_column(Text, default="", comment="最近采集错误")

    __table_args__ = (Index("ix_mcc_tenant", "tenant_id"),)


class MonitorPrivilegeApply(BaseModel):
    """
    监控查看权限申请表（走审批流，复用 AuditService）。
    """
    __tablename__ = "monitor_privilege_apply"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(50), nullable=False, comment="申请标题")
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="资源组ID")

    # 2.0 固定为 instance 级，3.0 启用 metric_group 粒度
    priv_scope: Mapped[str] = mapped_column(
        Enum("instance", "metric_group", name="monitor_priv_scope_enum"),
        default="instance",
        comment="权限粒度",
    )
    # 3.0 预留字段：指标分组（如 performance,replication）
    metric_groups: Mapped[str] = mapped_column(
        String(200), default="", comment="指标分组(3.0启用)"
    )
    valid_date: Mapped[date] = mapped_column(Date, nullable=False, comment="权限有效期")
    apply_reason: Mapped[str] = mapped_column(String(500), default="", comment="申请理由")
    # 复用 AuditStatus: 0待审 1通过 2驳回 3取消
    status: Mapped[int] = mapped_column(Integer, default=0, comment="审批状态")
    audit_auth_groups: Mapped[str] = mapped_column(String(255), default="", comment="审批链")

    __table_args__ = (
        Index("ix_mpa_user", "user_id"),
        Index("ix_mpa_status", "status"),
        Index("ix_mpa_tenant", "tenant_id"),
    )


class MonitorPrivilege(BaseModel):
    """
    已授权的监控查看权限记录。
    审批通过后由 AuditService 回调创建。
    """
    __tablename__ = "monitor_privilege"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apply_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("monitor_privilege_apply.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    priv_scope: Mapped[str] = mapped_column(String(20), default="instance")
    metric_groups: Mapped[str] = mapped_column(String(200), default="")
    valid_date: Mapped[date] = mapped_column(Date, nullable=False, comment="权限有效期")
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, comment="软删除")

    __table_args__ = (
        Index(
            "ix_mon_priv_lookup",
            "user_id", "instance_id", "valid_date", "is_deleted",
        ),
        Index("ix_mon_priv_tenant", "tenant_id"),
    )


class MonitorMetricSnapshot(BaseModel):
    """实例级监控指标采样快照。"""

    __tablename__ = "monitor_metric_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="success", comment="success/partial/failed")
    error: Mapped[str] = mapped_column(Text, default="", comment="采集错误")
    missing_groups: Mapped[dict] = mapped_column(JSON, default=dict, comment="缺失指标组原因")

    is_up: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(100), default="")
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    current_connections: Mapped[int | None] = mapped_column(Integer)
    active_sessions: Mapped[int | None] = mapped_column(Integer)
    max_connections: Mapped[int | None] = mapped_column(Integer)
    connection_usage: Mapped[float | None] = mapped_column(Float)
    qps: Mapped[float | None] = mapped_column(Float)
    tps: Mapped[float | None] = mapped_column(Float)
    slow_queries: Mapped[int | None] = mapped_column(BigInteger)
    error_count: Mapped[int | None] = mapped_column(BigInteger)
    lock_waits: Mapped[int | None] = mapped_column(Integer)
    long_transactions: Mapped[int | None] = mapped_column(Integer)
    replication_lag_seconds: Mapped[int | None] = mapped_column(Integer)
    total_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    extra_metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_mms_instance_time", "instance_id", "collected_at"),
        Index("ix_mms_tenant", "tenant_id"),
    )


class MonitorDatabaseCapacitySnapshot(BaseModel):
    """库/Schema 容量采样快照。"""

    __tablename__ = "monitor_database_capacity_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    db_name: Mapped[str] = mapped_column(String(128), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    data_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    index_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(30), default="success")
    error: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_mdcs_instance_time", "instance_id", "collected_at"),
        Index("ix_mdcs_db", "instance_id", "db_name"),
        Index("ix_mdcs_tenant", "tenant_id"),
    )


class MonitorTableCapacitySnapshot(BaseModel):
    """表/集合容量采样快照。"""

    __tablename__ = "monitor_table_capacity_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    db_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(256), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    index_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_mtcs_instance_time", "instance_id", "collected_at"),
        Index("ix_mtcs_table", "instance_id", "db_name", "table_name"),
        Index("ix_mtcs_total_size", "instance_id", "total_size_bytes"),
        Index("ix_mtcs_tenant", "tenant_id"),
    )
