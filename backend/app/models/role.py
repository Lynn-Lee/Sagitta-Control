"""
角色与用户组模型。

角色（Role）：权限码的集合，用户绑定 1 个角色。
用户组（UserGroup）：组织架构单元，关联资源组获得实例访问权。
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel

if TYPE_CHECKING:
    from app.models.user import Permission, ResourceGroup, Users

# ─── 关联表 ──────────────────────────────────────────────────

# 角色 ↔ 权限码（多对多）
role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("role.id", ondelete="CASCADE")),
    Column("permission_id", Integer, ForeignKey("permission.id", ondelete="CASCADE")),
)

# 用户组 ↔ 成员（多对多）
user_group_member = Table(
    "user_group_member",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("sql_users.id", ondelete="CASCADE")),
    Column("group_id", Integer, ForeignKey("user_group.id", ondelete="CASCADE")),
)

# 用户组 ↔ 资源组（多对多）
group_resource_group = Table(
    "group_resource_group",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("user_group.id", ondelete="CASCADE")),
    Column("resource_group_id", Integer, ForeignKey("resource_group.id", ondelete="CASCADE")),
)


class Role(BaseModel):
    """
    角色表：权限码的命名集合。

    内置角色（is_system=True）不可删除：
    - superadmin: 超级管理员，is_superuser=True，绕过一切检查
    - dba: 全局 DBA，拥有 query_all_instances + observability_instance_all
    - dba_group: 资源组 DBA，运维权限但实例范围限于资源组
    - developer: 开发工程师，工单提交 + 查询申请

    管理员可创建自定义角色并调整权限码，但不删除内置角色。
    """

    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="角色标识")
    name_cn: Mapped[str] = mapped_column(String(100), default="", comment="角色中文名")
    description: Mapped[str] = mapped_column(String(500), default="", comment="角色描述")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, comment="内置角色不可删除")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="停用后新用户不可分配")

    permissions: Mapped[list["Permission"]] = relationship(  # noqa: F821
        "Permission", secondary=role_permission, lazy="selectin"
    )

    __table_args__ = (Index("ix_role_tenant", "tenant_id"),)


class UserGroup(BaseModel):
    """
    用户组：组织架构单元（部门/团队）。

    - 有组长（leader_id），用于审批流自动路由
    - 支持树形层级（parent_id）
    - 通过 group_resource_group 关联资源组，获得实例访问权
    """

    __tablename__ = "user_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="组标识")
    name_cn: Mapped[str] = mapped_column(String(100), default="", comment="组中文名")
    description: Mapped[str] = mapped_column(String(500), default="", comment="组描述")

    leader_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sql_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="组长用户ID",
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_group.id", ondelete="SET NULL"),
        nullable=True,
        comment="父组ID（支持树形层级）",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    # 关联关系
    members: Mapped[list["Users"]] = relationship(  # noqa: F821
        "Users", secondary=user_group_member, back_populates="user_groups"
    )
    resource_groups: Mapped[list["ResourceGroup"]] = relationship(  # noqa: F821
        "ResourceGroup", secondary=group_resource_group, back_populates="user_groups"
    )
    leader: Mapped["Users | None"] = relationship("Users", foreign_keys=[leader_id])  # noqa: F821
    parent: Mapped["UserGroup | None"] = relationship(
        "UserGroup", remote_side="UserGroup.id", foreign_keys=[parent_id]
    )

    __table_args__ = (Index("ix_user_group_tenant", "tenant_id"),)
