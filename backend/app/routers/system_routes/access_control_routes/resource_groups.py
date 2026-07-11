"""系统访问控制子路由。"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.user import (
    ResourceGroupCreate,
    ResourceGroupUpdate,
)
from app.services.role import UserGroupService
from app.services.user import ResourceGroupService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 资源组管理
# ═══════════════════════════════════════════════════════════


@router.get("/resource-groups/", summary="资源组列表")
async def list_resource_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    total, items = await ResourceGroupService.list_groups(db, page, page_size, search)
    result = []
    for rg in items:
        mc = await ResourceGroupService.get_member_count(db, rg.id)
        ugs = await UserGroupService.get_user_groups_for_resource_group(db, rg.id)
        instances = (
            [
                {
                    "id": inst.id,
                    "instance_name": inst.instance_name,
                    "db_type": inst.db_type,
                    "host": inst.host,
                    "port": inst.port,
                    "is_active": inst.is_active,
                }
                for inst in rg.instances
                if inst.is_active
            ]
            if rg.instances
            else []
        )
        result.append(
            {
                "id": rg.id,
                "group_name": rg.group_name,
                "group_name_cn": rg.group_name_cn,
                "ding_webhook": rg.ding_webhook,
                "feishu_webhook": rg.feishu_webhook,
                "is_active": rg.is_active,
                "tenant_id": rg.tenant_id,
                "member_count": mc,
                "user_group_count": len(ugs),
                "user_groups": [
                    {"id": g.id, "name": g.name, "name_cn": g.name_cn}
                    for g in ugs
                ],
                "instances": instances,
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": result}


@router.post("/resource-groups/", summary="创建资源组")
async def create_resource_group(
    data: ResourceGroupCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("resource_group_manage")),
):
    rg = await ResourceGroupService.create(db, data)
    return {
        "status": 0,
        "msg": "资源组创建成功",
        "data": {"id": rg.id, "group_name": rg.group_name},
    }


@router.put("/resource-groups/{rg_id}/", summary="更新资源组")
async def update_resource_group(
    rg_id: int,
    data: ResourceGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("resource_group_manage")),
):
    rg = await ResourceGroupService.update(db, rg_id, data)
    return {"status": 0, "msg": "资源组已更新", "data": {"id": rg.id}}


@router.delete("/resource-groups/{rg_id}/", summary="删除资源组")
async def delete_resource_group(
    rg_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("resource_group_manage")),
):
    await ResourceGroupService.delete(db, rg_id)
    return {"status": 0, "msg": "资源组已删除"}


@router.get("/resource-groups/{rg_id}/members/", summary="资源组成员列表（通过用户组）")
async def list_rg_members(
    rg_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    """v2: 资源组成员通过用户组关联获取，不再直接查 user_resource_group。"""
    members = await UserGroupService.list_members_for_resource_group(db, rg_id)
    return {
        "items": [
            {"id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email}
            for u in members
        ]
    }


class MemberUpdateRequest(BaseModel):
    user_ids: list[int]


@router.post(
    "/resource-groups/{rg_id}/members/", summary="更新资源组成员（已废弃，请使用用户组关联）"
)
async def update_rg_members(
    rg_id: int,
    data: MemberUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("resource_group_manage")),
):
    """v2: 资源组成员管理已迁移到用户组体系，此端点仅为前端兼容保留空操作。"""
    return {
        "status": 0,
        "msg": "资源组成员管理已迁移到用户组体系，请使用 PUT /resource-groups/{id}/user-groups/",
    }


@router.get("/resource-groups/{rg_id}/user-groups/", summary="资源组关联的用户组")
async def list_rg_user_groups(
    rg_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
    groups = await UserGroupService.get_user_groups_for_resource_group(db, rg_id)
    return {
        "items": [
            {
                "id": g.id,
                "name": g.name,
                "name_cn": g.name_cn,
            }
            for g in groups
        ]
    }


class RgUserGroupsUpdateRequest(BaseModel):
    user_group_ids: list[int]


@router.put("/resource-groups/{rg_id}/user-groups/", summary="更新资源组关联的用户组")
async def update_rg_user_groups(
    rg_id: int,
    data: RgUserGroupsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("resource_group_manage")),
):
    await UserGroupService.update_resource_group_user_groups(db, rg_id, data.user_group_ids)
    return {"status": 0, "msg": f"资源组用户组关联已更新，共 {len(data.user_group_ids)} 个组"}
