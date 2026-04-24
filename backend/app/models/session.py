"""Database session snapshot models."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
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
    time_seconds: Mapped[int] = mapped_column(Integer, default=0, comment="运行秒数")
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
