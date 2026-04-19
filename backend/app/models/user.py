"""
用户、权限组、资源组相关模型。

Phase 4 已完成：移除 user_permission 和 user_resource_group 旧关联表。
权限通过 Role → role_permission 获取，用户通过 UserGroup → ResourceGroup 获取资源组。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel

# ─── 关联表（多对多）─────────────────────────────────────────
instance_resource_group = Table(
    "instance_resource_group",
    Base.metadata,
    Column("instance_id", Integer, ForeignKey("sql_instance.id", ondelete="CASCADE")),
    Column("resource_group_id", Integer, ForeignKey("resource_group.id", ondelete="CASCADE")),
)


class Users(BaseModel):
    """用户表。"""

    __tablename__ = "sql_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, comment="用户名")
    display_name: Mapped[str] = mapped_column(String(50), default="", comment="显示名称")
    password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码哈希")
    email: Mapped[str] = mapped_column(String(100), default="", comment="邮箱")
    phone: Mapped[str] = mapped_column(String(20), default="", comment="手机号")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否超级管理员")

    # 认证来源（local / ldap / oidc / dingtalk）
    auth_type: Mapped[str] = mapped_column(String(20), default="local", comment="认证来源")
    # 外部系统 ID（LDAP dn、OIDC sub 等）
    external_id: Mapped[str] = mapped_column(String(200), default="", comment="外部认证ID")

    # 2FA
    totp_secret: Mapped[str | None] = mapped_column(String(500), comment="TOTP 密钥（加密）")
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用 2FA")

    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")

    # ── v2: 角色、组织、直属上级 ──────────────────────────────
    role_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("role.id", ondelete="SET NULL"),
        nullable=True,
        comment="角色ID（单角色）",
    )
    manager_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="直属上级用户ID",
    )
    employee_id: Mapped[str] = mapped_column(String(50), default="", comment="工号")
    department: Mapped[str] = mapped_column(String(100), default="", comment="部门")
    title: Mapped[str] = mapped_column(String(100), default="", comment="职位/岗位")
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="最近一次密码修改时间"
    )

    # ── relationships ────────────────────────────────────────────
    user_groups: Mapped[list["UserGroup"]] = relationship(  # noqa: F821
        "UserGroup", secondary="user_group_member", back_populates="members"
    )
    role: Mapped["Role | None"] = relationship("Role", foreign_keys=[role_id])  # noqa: F821
    manager: Mapped["Users | None"] = relationship(  # noqa: F821
        "Users", remote_side="Users.id", foreign_keys=[manager_id]
    )

    __table_args__ = (
        Index("ix_users_tenant", "tenant_id"),
        Index("ix_users_auth_type", "auth_type"),
    )


class ResourceGroup(BaseModel):
    """
    资源组：隔离不同团队对实例的访问权限。

    v2：资源组只包含实例，不再直接包含用户。
    用户通过 用户组 → 资源组 → 实例 链路获得访问权。
    """

    __tablename__ = "resource_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="资源组名称"
    )
    group_name_cn: Mapped[str] = mapped_column(String(100), default="", comment="资源组中文名")
    ding_webhook: Mapped[str] = mapped_column(String(500), default="", comment="钉钉 Webhook")
    feishu_webhook: Mapped[str] = mapped_column(String(500), default="", comment="飞书 Webhook")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    instances: Mapped[list["Instance"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Instance", secondary=instance_resource_group, back_populates="resource_groups"
    )
    user_groups: Mapped[list["UserGroup"]] = relationship(  # noqa: F821
        "UserGroup", secondary="group_resource_group", back_populates="resource_groups"
    )

    __table_args__ = (Index("ix_rg_tenant", "tenant_id"),)


class Permission(BaseModel):
    """自定义权限表。v2：权限通过 Role → Permission 关联（role_permission）。"""

    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codename: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="权限码"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="权限说明")
