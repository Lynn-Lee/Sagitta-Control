"""Database session snapshot models."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SessionSnapshot(BaseModel):
    """Periodic snapshot of database sessions for history view."""

    __tablename__ = "session_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="采集时间"
    )
    instance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="SET NULL"), nullable=True
    )
    instance_name: Mapped[str] = mapped_column(String(100), default="", comment="实例名称快照")
    db_type: Mapped[str] = mapped_column(String(20), default="", comment="数据库类型快照")
    session_id: Mapped[str] = mapped_column(String(128), default="", comment="会话ID")
    serial: Mapped[str] = mapped_column(String(128), default="", comment="Oracle SERIAL# 等二级标识")
    username: Mapped[str] = mapped_column(String(128), default="", comment="数据库用户")
    host: Mapped[str] = mapped_column(String(255), default="", comment="客户端主机")
    program: Mapped[str] = mapped_column(String(255), default="", comment="客户端程序")
    db_name: Mapped[str] = mapped_column(String(128), default="", comment="数据库/Schema")
    command: Mapped[str] = mapped_column(String(128), default="", comment="命令类型")
    state: Mapped[str] = mapped_column(String(255), default="", comment="会话状态")
    time_seconds: Mapped[int] = mapped_column(Integer, default=0, comment="运行秒数（兼容字段）")
    duration_ms: Mapped[int] = mapped_column(BigInteger, default=0, comment="运行耗时(毫秒)")
    connection_age_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="连接/会话存活时长(毫秒)")
    state_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="当前状态持续时长(毫秒)")
    active_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="当前活动/操作持续时长(毫秒)")
    transaction_age_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="当前事务持续时长(毫秒)")
    duration_source: Mapped[str] = mapped_column(String(64), default="", comment="时长来源说明")
    sql_id: Mapped[str] = mapped_column(String(64), default="", comment="SQL ID")
    sql_text: Mapped[str] = mapped_column(Text, default="", comment="SQL 文本")
    event: Mapped[str] = mapped_column(String(255), default="", comment="等待事件")
    blocking_session: Mapped[str] = mapped_column(String(128), default="", comment="阻塞会话")
    source: Mapped[str] = mapped_column(String(32), default="platform", comment="采集来源")
    collect_error: Mapped[str] = mapped_column(Text, default="", comment="采集错误")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, comment="原始会话行")

    __table_args__ = (
        Index("ix_session_snapshot_inst_time", "instance_id", "collected_at"),
        Index("ix_session_snapshot_db_type_time", "db_type", "collected_at"),
        Index("ix_session_snapshot_user", "username"),
        Index("ix_session_snapshot_session", "session_id", "serial"),
        Index("ix_session_snapshot_tenant", "tenant_id"),
    )


class SessionCollectConfig(BaseModel):
    """Instance-level session snapshot collection policy."""

    __tablename__ = "session_collect_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sql_instance.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="实例ID",
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用会话采集")
    collect_interval: Mapped[int] = mapped_column(Integer, default=60, comment="采集间隔(秒)")
    retention_days: Mapped[int] = mapped_column(Integer, default=30, comment="保留天数")
    last_collect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近采集时间")
    last_collect_status: Mapped[str] = mapped_column(String(20), default="never", comment="never/success/failed/skipped")
    last_collect_error: Mapped[str] = mapped_column(Text, default="", comment="最近采集错误")
    last_collect_count: Mapped[int] = mapped_column(Integer, default=0, comment="最近新增条数")
    created_by: Mapped[str] = mapped_column(String(100), default="", comment="创建人")

    __table_args__ = (
        Index("ix_sessioncfg_instance", "instance_id"),
        Index("ix_sessioncfg_enabled", "is_enabled"),
        Index("ix_sessioncfg_tenant", "tenant_id"),
    )
