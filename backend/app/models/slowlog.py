"""Slow query log models."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SlowQueryLog(BaseModel):
    """Unified slow SQL record from platform history or native engine collectors."""

    __tablename__ = "slow_query_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, comment="platform/mysql_slowlog/pgsql_statements/redis_slowlog")
    source_ref: Mapped[str] = mapped_column(String(128), default="", comment="来源内去重标识")
    instance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="SET NULL"), nullable=True
    )
    instance_name: Mapped[str] = mapped_column(String(100), default="", comment="实例名称快照")
    db_type: Mapped[str] = mapped_column(String(20), default="", comment="数据库类型快照")
    db_name: Mapped[str] = mapped_column(String(128), default="", comment="数据库/Schema")
    sql_text: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 文本")
    sql_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, comment="SQL 指纹")
    fingerprint_text: Mapped[str] = mapped_column(Text, default="", comment="归一化 SQL")
    duration_ms: Mapped[int] = mapped_column(BigInteger, default=0, comment="执行耗时(ms)")
    rows_examined: Mapped[int] = mapped_column(BigInteger, default=0, comment="扫描行数")
    rows_sent: Mapped[int] = mapped_column(BigInteger, default=0, comment="返回行数")
    username: Mapped[str] = mapped_column(String(128), default="", comment="数据库/平台用户")
    client_host: Mapped[str] = mapped_column(String(255), default="", comment="客户端主机")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="发生时间")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False, comment="原始数据")
    analysis_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False, comment="分析标签")
    collect_error: Mapped[str] = mapped_column(Text, default="", comment="采集错误")

    __table_args__ = (
        UniqueConstraint("source", "source_ref", name="uq_slowlog_source_ref"),
        Index("ix_slowlog_instance_time", "instance_id", "occurred_at"),
        Index("ix_slowlog_fingerprint", "sql_fingerprint"),
        Index("ix_slowlog_source", "source"),
        Index("ix_slowlog_db_type_time", "db_type", "occurred_at"),
        Index("ix_slowlog_tenant", "tenant_id"),
    )


class SlowQueryConfig(BaseModel):
    """Instance-level slow query collection policy and last collection status."""

    __tablename__ = "slow_query_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sql_instance.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="实例ID",
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用慢日志采集")
    threshold_ms: Mapped[int] = mapped_column(Integer, default=1000, comment="慢 SQL 阈值(ms)")
    collect_interval: Mapped[int] = mapped_column(Integer, default=300, comment="采集间隔(秒)")
    retention_days: Mapped[int] = mapped_column(Integer, default=30, comment="保留天数")
    collect_limit: Mapped[int] = mapped_column(Integer, default=100, comment="单次采集上限")
    last_collect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近采集时间")
    last_collect_status: Mapped[str] = mapped_column(String(20), default="never", comment="never/success/partial/failed/unsupported")
    last_collect_error: Mapped[str] = mapped_column(Text, default="", comment="最近采集错误")
    last_collect_count: Mapped[int] = mapped_column(Integer, default=0, comment="最近新增条数")
    created_by: Mapped[str] = mapped_column(String(100), default="", comment="创建人")

    __table_args__ = (
        Index("ix_slowcfg_instance", "instance_id"),
        Index("ix_slowcfg_enabled", "is_enabled"),
        Index("ix_slowcfg_tenant", "tenant_id"),
    )
