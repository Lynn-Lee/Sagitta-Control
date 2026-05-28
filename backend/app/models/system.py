"""
系统配置 & 操作审计日志模型。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SystemConfig(BaseModel):
    """
    系统配置表（KV 结构）。
    敏感值（密码/Token）用 encrypt_field 加密存储。
    """
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="配置键")
    config_value: Mapped[str] = mapped_column(Text, default="", comment="配置值")
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, comment="值是否已加密")
    description: Mapped[str] = mapped_column(String(200), default="", comment="描述")
    group: Mapped[str] = mapped_column(String(50), default="basic", comment="分组")

    __table_args__ = (
        Index("ix_syscfg_group", "group"),
        Index("ix_syscfg_tenant", "tenant_id"),
    )


class OperationLog(BaseModel):
    """
    操作审计日志。
    记录所有用户的写操作（登录/工单/权限变更等）。
    """
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=0, comment="操作人ID")
    username: Mapped[str] = mapped_column(String(30), default="", comment="操作人用户名")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作类型")
    module: Mapped[str] = mapped_column(String(50), default="", comment="功能模块")
    detail: Mapped[str] = mapped_column(Text, default="", comment="操作详情")
    ip_address: Mapped[str] = mapped_column(String(50), default="", comment="客户端IP")
    result: Mapped[str] = mapped_column(String(10), default="success", comment="success/fail")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")

    __table_args__ = (
        Index("ix_oplog_user", "user_id"),
        Index("ix_oplog_action", "action"),
        Index("ix_oplog_module", "module"),
        Index("ix_oplog_tenant", "tenant_id"),
    )


class NotificationDeliveryLog(BaseModel):
    """主动通知投递日志。"""

    __tablename__ = "notification_delivery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="通知事件")
    subject_type: Mapped[str] = mapped_column(String(30), default="", comment="对象类型")
    subject_id: Mapped[int] = mapped_column(Integer, default=0, comment="对象ID")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, comment="通知渠道")
    recipient_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="SET NULL"), nullable=True, comment="收件用户ID"
    )
    recipient: Mapped[str] = mapped_column(String(200), default="", comment="收件地址/外部ID")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="sent/failed/skipped")
    error: Mapped[str] = mapped_column(Text, default="", comment="失败原因")

    __table_args__ = (
        Index("ix_notify_event", "event_type"),
        Index("ix_notify_subject", "subject_type", "subject_id"),
        Index("ix_notify_user", "recipient_user_id"),
        Index("ix_notify_status", "status"),
        Index("ix_notify_tenant", "tenant_id"),
    )


class LicenseRecord(BaseModel):
    """商业授权记录。"""

    __tablename__ = "license_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), default="trial", comment="trial/import/offline/online")
    status: Mapped[str] = mapped_column(String(20), default="trial", comment="trial/licensed/invalid/expired")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否当前授权")
    raw_license: Mapped[str] = mapped_column(Text, default="", comment="原始 license JSON")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="License payload")
    signature: Mapped[str] = mapped_column(Text, default="", comment="License 签名")
    license_id: Mapped[str] = mapped_column(String(100), default="", comment="License ID")
    customer_id: Mapped[str] = mapped_column(String(100), default="", comment="客户 ID")
    company_name: Mapped[str] = mapped_column(String(200), default="", comment="客户名称")
    edition: Mapped[str] = mapped_column(String(50), default="trial", comment="版本")
    features: Mapped[list] = mapped_column(JSON, default=list, comment="授权功能")
    limits: Mapped[dict] = mapped_column(JSON, default=dict, comment="授权额度")
    activation_code: Mapped[str] = mapped_column(String(100), default="", comment="激活码")
    activation_id: Mapped[str] = mapped_column(String(100), default="", comment="在线激活 ID")
    server_url: Mapped[str] = mapped_column(String(500), default="", comment="授权服务器地址")
    remote_status: Mapped[str] = mapped_column(String(20), default="", comment="授权服务器返回状态")
    deployment_fingerprint: Mapped[str] = mapped_column(String(100), default="", comment="部署指纹")
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="签发时间"
    )
    not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="生效时间"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间"
    )
    last_online_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后联网校验时间"
    )
    last_check_status: Mapped[str] = mapped_column(String(20), default="ok", comment="最后检查状态")
    last_check_reason: Mapped[str] = mapped_column(String(500), default="", comment="最后检查原因")

    __table_args__ = (
        Index("ix_license_current", "is_current"),
        Index("ix_license_status", "status"),
        Index("ix_license_customer", "customer_id"),
        Index("ix_license_expires", "expires_at"),
        Index("ix_license_deployment_fingerprint", "deployment_fingerprint"),
        Index("ix_license_tenant", "tenant_id"),
    )


class DeliveryAcceptanceRun(BaseModel):
    """商业交付验收运行记录。"""

    __tablename__ = "delivery_acceptance_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), default="success", comment="success/failed")
    options: Mapped[dict] = mapped_column(JSON, default=dict, comment="验收选项")
    report_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="结构化验收报告")
    report_markdown: Mapped[str] = mapped_column(Text, default="", comment="Markdown 验收报告")
    created_by: Mapped[str] = mapped_column(String(100), default="", comment="创建人")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )

    __table_args__ = (
        Index("ix_delivery_run_status", "status"),
        Index("ix_delivery_run_tenant", "tenant_id"),
    )


class DiagnosticBundle(BaseModel):
    """商业支持诊断包记录。"""

    __tablename__ = "diagnostic_bundle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), default="success", comment="success/failed")
    bundle_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="脱敏后的诊断内容")
    created_by: Mapped[str] = mapped_column(String(100), default="", comment="创建人")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )

    __table_args__ = (
        Index("ix_diagnostic_bundle_status", "status"),
        Index("ix_diagnostic_bundle_tenant", "tenant_id"),
    )
