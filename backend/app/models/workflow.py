"""
SQL 工单相关模型。
关键改进：WorkflowStatus 统一为整数枚举，消除 Archery 1.x 字符串状态混乱（P1-1）。
"""
from datetime import datetime
from enum import IntEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WorkflowStatus(IntEnum):
    """
    工单状态（整数枚举）。
    对应 Archery 1.x 字符串值（已废弃）：
      0 ← workflow_manreviewing
      1 ← workflow_autoreviewwrong
      2 ← workflow_review_pass
      3 ← workflow_timingtask
      4 ← workflow_queuing
      5 ← workflow_executing
      6 ← workflow_finish
      7 ← workflow_exception
      8 ← workflow_abort
    """
    PENDING_REVIEW   = 0
    AUTO_REVIEW_FAIL = 1
    REVIEW_PASS      = 2
    TIMING_TASK      = 3
    QUEUING          = 4
    EXECUTING        = 5
    FINISH           = 6
    EXCEPTION        = 7
    ABORT            = 8


class WorkflowType(IntEnum):
    QUERY   = 1   # 查询权限申请
    SQL     = 2   # SQL 上线工单
    ARCHIVE = 3   # 数据归档申请
    MONITOR = 4   # 监控查看权限申请


class AuditStatus(IntEnum):
    PENDING  = 0   # 待审核
    PASSED   = 1   # 已通过
    REJECTED = 2   # 已驳回
    CANCELED = 3   # 已取消


class SqlWorkflow(BaseModel):
    """SQL 上线工单主表。"""
    __tablename__ = "sql_workflow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="工单名称")
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="资源组ID")
    group_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="资源组名称")

    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="RESTRICT"), nullable=False
    )
    db_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="目标数据库名")

    # 0=未知 1=DDL 2=DML 3=导出
    syntax_type: Mapped[int] = mapped_column(Integer, default=0, comment="SQL类型")
    is_backup: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否备份")

    engineer: Mapped[str] = mapped_column(String(30), nullable=False, comment="提交人用户名")
    engineer_display: Mapped[str] = mapped_column(String(50), default="", comment="提交人显示名")
    engineer_id: Mapped[int] = mapped_column(Integer, ForeignKey("sql_users.id"), nullable=False)

    # 整数枚举状态（修复 1.x 字符串状态混乱）
    status: Mapped[int] = mapped_column(
        Integer, default=WorkflowStatus.PENDING_REVIEW, nullable=False, comment="工单状态"
    )

    # 审批链（逗号分隔的权限组ID，如 "1,2,3"）
    audit_auth_groups: Mapped[str] = mapped_column(
        String(255), default="", comment="审批链权限组"
    )

    run_date_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="可执行时间窗口开始"
    )
    run_date_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="可执行时间窗口结束"
    )
    execute_mode: Mapped[str | None] = mapped_column(
        String(20), comment="执行方式：immediate/scheduled/external"
    )
    scheduled_execute_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="预约平台执行时间"
    )
    executed_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="SET NULL"), nullable=True, comment="执行决策人ID"
    )
    executed_by_name: Mapped[str | None] = mapped_column(
        String(100), comment="执行决策人名称"
    )
    external_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="外部实际执行时间"
    )
    external_result_status: Mapped[str | None] = mapped_column(
        String(20), comment="外部执行结果：success/failed"
    )
    external_result_remark: Mapped[str | None] = mapped_column(
        String(500), comment="外部执行结果备注"
    )
    finish_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="实际执行完成时间"
    )

    # 审批流模板（多级审批时使用）
    flow_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("approval_flow.id", ondelete="SET NULL"),
        nullable=True, comment="审批流模板ID"
    )

    # 数据导出工单专用
    export_format: Mapped[str | None] = mapped_column(
        String(10), comment="导出格式（csv/xlsx/json）"
    )

    # SQL 内容单独表（支持大字段，避免主表膨胀）
    content: Mapped["SqlWorkflowContent"] = relationship(
        "SqlWorkflowContent", back_populates="workflow",
        uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_workflow_status", "status"),
        Index("ix_workflow_engineer", "engineer_id"),
        Index("ix_workflow_instance", "instance_id"),
        Index("ix_workflow_scheduled_execute", "status", "scheduled_execute_at"),
        Index("ix_workflow_tenant", "tenant_id"),
    )


class SqlWorkflowContent(BaseModel):
    """SQL 工单内容表（大字段分离存储）。"""
    __tablename__ = "sql_workflow_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_workflow.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    sql_content: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 内容")
    # 自动审核结果（JSON 字符串）
    review_content: Mapped[str] = mapped_column(Text, default="", comment="审核结果JSON")
    # 执行结果（JSON 字符串）
    execute_result: Mapped[str] = mapped_column(Text, default="", comment="执行结果JSON")
    # 提交时风险预案快照（JSON 字符串）
    risk_plan: Mapped[str] = mapped_column(Text, default="", comment="风险预案JSON")
    risk_remark: Mapped[str] = mapped_column(String(500), default="", comment="申请人风险说明")

    workflow: Mapped[SqlWorkflow] = relationship("SqlWorkflow", back_populates="content")


class WorkflowAudit(BaseModel):
    """审批记录表（记录每个节点的审批人和操作）。"""
    __tablename__ = "workflow_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_workflow.id", ondelete="CASCADE"), nullable=False
    )
    workflow_type: Mapped[int] = mapped_column(Integer, nullable=False, comment="工单类型")
    workflow_title: Mapped[str] = mapped_column(String(50), default="", comment="工单标题")

    # 当前审批节点（步骤序号，从 1 开始）
    current_audit_auth_group: Mapped[str] = mapped_column(
        String(255), default="", comment="当前审批权限组"
    )
    current_status: Mapped[int] = mapped_column(
        Integer, default=AuditStatus.PENDING, comment="当前审批状态"
    )
    # 完整审批链
    audit_auth_groups: Mapped[str] = mapped_column(
        String(255), default="", comment="完整审批链"
    )
    audit_auth_groups_info: Mapped[str] = mapped_column(
        Text, default="", comment="审批链详情JSON"
    )

    create_user: Mapped[str] = mapped_column(String(30), default="", comment="创建人")
    create_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("sql_users.id"))

    __table_args__ = (
        Index("ix_audit_workflow", "workflow_id"),
        Index("ix_audit_type_status", "workflow_type", "current_status"),
    )


class WorkflowLog(BaseModel):
    """审批操作日志（每次操作记录一条）。"""
    __tablename__ = "workflow_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_audit.id", ondelete="CASCADE"), nullable=False
    )
    operator: Mapped[str] = mapped_column(String(30), nullable=False, comment="操作人")
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("sql_users.id"))
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="操作类型")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="操作备注")

    __table_args__ = (Index("ix_workflowlog_audit", "audit_id"),)
