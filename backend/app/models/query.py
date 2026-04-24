"""
查询权限与查询日志模型。

v2-lite 首发口径：
- 查询授权主路径仅启用用户主体
- scope_type 首发仅使用 database / table
- user_group_id / resource_group_id 作为兼容位保留
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QueryPrivilege(BaseModel):
    """查询权限记录（库级或表级）。

    v2-lite 首发：
    - 授权主体：用户
    - 授权粒度：database / table

    user_group_id / resource_group_id 仅作为兼容字段保留。
    """

    __tablename__ = "query_privilege"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_users.id", ondelete="CASCADE"),
        nullable=True,
        comment="被授权用户ID（用户授权时非空）",
    )
    user_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_group.id", ondelete="CASCADE"),
        nullable=True,
        comment="被授权用户组ID（用户组授权时非空）",
    )
    instance_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_instance.id", ondelete="CASCADE"),
        nullable=True,
        comment="实例ID（scope_type=database/table 时非空）",
    )
    resource_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resource_group.id", ondelete="CASCADE"),
        nullable=True,
        comment="资源组ID（兼容预留字段）",
    )
    # scope_type 首发仅使用：database / table
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default="database",
        comment="授权粒度: database|table（兼容预留更细粒度）",
    )
    db_name: Mapped[str] = mapped_column(String(64), default="", comment="数据库名")
    table_name: Mapped[str] = mapped_column(String(64), default="", comment="表名（空=库级权限）")
    valid_date: Mapped[date] = mapped_column(Date, nullable=False, comment="权限有效期")
    limit_num: Mapped[int] = mapped_column(Integer, default=100, comment="单次查询行数限制")
    # 1=DATABASE 级 2=TABLE 级（兼容旧数据，新数据优先看 scope_type）
    priv_type: Mapped[int] = mapped_column(Integer, default=1, comment="权限粒度")
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, comment="软删除标志")
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="撤销时间"
    )
    revoked_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="撤销人ID",
    )
    revoked_by_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="撤销人名称")
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="撤销原因")

    __table_args__ = (
        Index(
            "ix_priv_user_inst_date",
            "user_id",
            "instance_id",
            "valid_date",
            "is_deleted",
        ),
        Index("ix_priv_tenant", "tenant_id"),
        Index("ix_priv_user_group", "user_group_id"),
        Index("ix_priv_scope_type", "scope_type"),
        Index("ix_priv_resource_group", "resource_group_id"),
        Index("ix_priv_revoked_at", "revoked_at"),
    )


class QueryPrivilegeApply(BaseModel):
    """查询权限申请表（走审批流）。

    v2-lite 首发仅申请用户自己的 database / table 查询权限。
    """

    __tablename__ = "query_privilege_apply"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(50), nullable=False, comment="申请标题")
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="CASCADE"), nullable=False
    )
    user_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_group.id", ondelete="SET NULL"),
        nullable=True,
        comment="授权给用户组（兼容预留，为空则授权给用户自己）",
    )
    instance_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_instance.id", ondelete="CASCADE"),
        nullable=True,
        comment="实例ID（scope_type=database/table 时非空）",
    )
    resource_group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resource_group.id", ondelete="SET NULL"),
        nullable=True,
        comment="资源组ID（兼容预留字段）",
    )
    # 保留 group_id 向后兼容（值等于 resource_group_id）
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="资源组ID（兼容旧字段）")
    # scope_type 首发仅使用：database / table
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default="database",
        comment="申请粒度: database|table（兼容预留更细粒度）",
    )
    db_name: Mapped[str] = mapped_column(String(64), default="", comment="数据库名")
    table_name: Mapped[str] = mapped_column(String(64), default="", comment="表名")
    valid_date: Mapped[date] = mapped_column(Date, nullable=False, comment="申请有效期")
    limit_num: Mapped[int] = mapped_column(Integer, default=100, comment="行数限制")
    priv_type: Mapped[int] = mapped_column(Integer, default=1)
    apply_reason: Mapped[str] = mapped_column(String(500), default="", comment="申请理由")
    # 复用 AuditStatus: 0待审 1通过 2驳回 3取消
    status: Mapped[int] = mapped_column(Integer, default=0, comment="审批状态")
    audit_auth_groups: Mapped[str] = mapped_column(String(255), default="", comment="审批链")
    flow_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("approval_flow.id", ondelete="SET NULL"),
        nullable=True,
        comment="审批流模板ID",
    )
    audit_auth_groups_info: Mapped[str] = mapped_column(
        Text,
        default="",
        comment="审批链详情JSON",
    )

    __table_args__ = (
        Index("ix_qpa_user", "user_id"),
        Index("ix_qpa_status", "status"),
        Index("ix_qpa_user_group", "user_group_id"),
        Index("ix_qpa_scope_type", "scope_type"),
        Index("ix_qpa_flow_id", "flow_id"),
    )


class QueryLog(BaseModel):
    """
    查询日志（记录每次在线查询）。
    修复 1.x TODO：user_id / instance_id 改为外键。
    """

    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_users.id", ondelete="SET NULL"), nullable=True
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="SET NULL"), nullable=True
    )
    db_name: Mapped[str] = mapped_column(String(64), default="", comment="数据库名")
    sqllog: Mapped[str] = mapped_column(Text, nullable=False, comment="执行的 SQL")
    operation_type: Mapped[str] = mapped_column(
        String(20), default="execute", comment="操作类型：execute/export"
    )
    export_format: Mapped[str] = mapped_column(String(10), default="", comment="导出格式")
    username: Mapped[str] = mapped_column(String(100), default="", comment="操作人快照")
    instance_name: Mapped[str] = mapped_column(String(100), default="", comment="实例名称快照")
    db_type: Mapped[str] = mapped_column(String(20), default="", comment="数据库类型快照")
    client_ip: Mapped[str] = mapped_column(String(50), default="", comment="客户端IP")
    error: Mapped[str] = mapped_column(Text, default="", comment="失败原因")
    effect_row: Mapped[int] = mapped_column(BigInteger, default=0, comment="影响行数")
    cost_time_ms: Mapped[int] = mapped_column(Integer, default=0, comment="执行耗时(ms)")
    # 权限校验是否通过
    priv_check: Mapped[bool] = mapped_column(Boolean, default=False, comment="权限校验通过")
    # 是否命中脱敏规则
    hit_rule: Mapped[bool] = mapped_column(Boolean, default=False, comment="命中脱敏规则")
    # 是否实际执行了脱敏
    masking: Mapped[bool] = mapped_column(Boolean, default=False, comment="已脱敏")
    # 是否收藏
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, comment="已收藏")

    __table_args__ = (
        Index("ix_qlog_user_date", "user_id", "created_at"),
        Index("ix_qlog_instance", "instance_id"),
        Index("ix_qlog_operation_type", "operation_type"),
        Index("ix_qlog_tenant", "tenant_id"),
    )
