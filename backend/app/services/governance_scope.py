"""统一治理视角解析。

视角只决定数据可见范围；具体操作权限仍由业务服务自行判断。
"""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instance import Instance
from app.models.role import UserGroup
from app.models.user import ResourceGroup

ScopeDomain = Literal["query", "workflow"]


class GovernanceScopeService:
    @staticmethod
    def is_global_user(user: dict, domain: ScopeDomain) -> bool:
        if user.get("is_superuser") or user.get("role") in {"superadmin", "dba"}:
            return True
        permissions = set(user.get("permissions", []))
        return domain == "query" and "query_all_instances" in permissions

    @staticmethod
    def _has_instance_scope_permission(user: dict, domain: ScopeDomain) -> bool:
        if user.get("role") == "dba_group":
            return True
        permissions = set(user.get("permissions", []))
        if domain == "query":
            return bool(permissions & {"query_mgtpriv", "query_resource_group_instance"})
        return "sql_execute_for_resource_group" in permissions

    @staticmethod
    async def _resolve_instance_ids(db: AsyncSession, user: dict) -> list[int]:
        user_rg_ids = user.get("resource_groups", [])
        if not user_rg_ids:
            return []
        result = await db.execute(
            select(Instance.id)
            .join(Instance.resource_groups.of_type(ResourceGroup))
            .where(and_(Instance.is_active.is_(True), ResourceGroup.id.in_(user_rg_ids)))
            .distinct()
        )
        return list(result.scalars().all())

    @staticmethod
    async def _resolve_group_user_ids(db: AsyncSession, user: dict) -> list[int]:
        leader_groups = await db.execute(
            select(UserGroup)
            .options(selectinload(UserGroup.members))
            .where(and_(UserGroup.leader_id == user["id"], UserGroup.is_active.is_(True)))
        )
        groups = leader_groups.scalars().all()
        if not groups:
            return []

        user_ids = {user["id"]}
        for group in groups:
            user_ids.update(member.id for member in group.members if member.is_active)
        return sorted(user_ids)

    @staticmethod
    async def resolve(db: AsyncSession, user: dict, domain: ScopeDomain) -> dict[str, Any]:
        if GovernanceScopeService.is_global_user(user, domain):
            return {"mode": "global", "label": "全量数据", "user_ids": None, "instance_ids": None}

        if GovernanceScopeService._has_instance_scope_permission(user, domain):
            return {
                "mode": "instance_scope",
                "label": "权限实例范围",
                "user_ids": None,
                "instance_ids": await GovernanceScopeService._resolve_instance_ids(db, user),
            }

        group_user_ids = await GovernanceScopeService._resolve_group_user_ids(db, user)
        if group_user_ids:
            return {
                "mode": "group",
                "label": "组内数据",
                "user_ids": group_user_ids,
                "instance_ids": None,
            }

        return {"mode": "self", "label": "我的数据", "user_ids": [user["id"]], "instance_ids": None}

    @staticmethod
    def apply_scope(stmt, scope: dict, *, user_col, instance_col):
        if scope["mode"] in {"self", "group"}:
            user_ids = scope.get("user_ids") or []
            if not user_ids:
                return stmt.where(user_col == -1)
            return stmt.where(user_col.in_(user_ids))
        if scope["mode"] == "instance_scope":
            instance_ids = scope.get("instance_ids") or []
            if not instance_ids:
                return stmt.where(instance_col == -1)
            return stmt.where(instance_col.in_(instance_ids))
        return stmt
