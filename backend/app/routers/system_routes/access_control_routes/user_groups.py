"""系统访问控制子路由。"""

from typing import Any
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.role import (
    UserGroupCreate,
    UserGroupUpdate,
)
from app.services.role import UserGroupService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 用户组管理
# ═══════════════════════════════════════════════════════════


@router.get("/user-groups/", summary="用户组列表")
async def list_user_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: bool | None = None,
    parent_id: int | None = None,
    search: str | None = None,
    leader_ids: list[int] | None = Query(None),
    parent_ids: list[int] | None = Query(None),
    resource_group_ids: list[int] | None = Query(None),
    statuses: list[bool] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    total, items = await UserGroupService.list_groups(
        db,
        page,
        page_size,
        is_active,
        parent_id,
        search,
        None,
        leader_ids,
        parent_ids,
        resource_group_ids,
        statuses,
    )
    result = []
    for g in items:
        result.append(
            {
                "id": g.id,
                "name": g.name,
                "name_cn": g.name_cn,
                "description": g.description,
                "leader_id": g.leader_id,
                "parent_id": g.parent_id,
                "is_active": g.is_active,
                "tenant_id": g.tenant_id,
                "member_count": len(g.members),
                "resource_group_ids": [rg.id for rg in g.resource_groups],
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": result}


@router.get("/user-groups/export/", summary="导出用户组")
async def export_user_groups(
    export_format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    search: str | None = None,
    is_active: bool | None = None,
    parent_id: int | None = None,
    group_ids: list[int] | None = Query(None),
    leader_ids: list[int] | None = Query(None),
    parent_ids: list[int] | None = Query(None),
    resource_group_ids: list[int] | None = Query(None),
    statuses: list[bool] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> StreamingResponse:
    rows = await UserGroupService.export_groups(
        db,
        search=search,
        is_active=is_active,
        parent_id=parent_id,
        group_ids=group_ids,
        leader_ids=leader_ids,
        parent_ids=parent_ids,
        resource_group_ids=resource_group_ids,
        statuses=statuses,
    )
    content, media_type, filename = UserGroupService.build_group_export_file(rows, export_format)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


@router.get("/user-groups/import-template/", summary="下载用户组导入模板")
async def download_user_group_import_template(
    export_format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> StreamingResponse:
    content, media_type, filename = UserGroupService.build_group_import_template(export_format)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


@router.post("/user-groups/import/", summary="导入用户组")
async def import_user_groups(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    result = await UserGroupService.import_groups(
        db=db,
        filename=file.filename or "",
        content=await file.read(),
    )
    return {"status": 0, "msg": "用户组导入完成", "data": result}


@router.post("/user-groups/", summary="创建用户组")
async def create_user_group(
    data: UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    group = await UserGroupService.create_group(
        db,
        name=data.name,
        name_cn=data.name_cn,
        description=data.description,
        leader_id=data.leader_id,
        parent_id=data.parent_id,
        resource_group_ids=data.resource_group_ids,
        member_ids=data.member_ids,
    )
    return {"status": 0, "msg": "用户组创建成功", "data": {"id": group.id, "name": group.name}}


@router.get("/user-groups/{group_id}/", summary="用户组详情")
async def get_user_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    group = await UserGroupService.get_by_id(db, group_id)
    if not group:
        from fastapi import HTTPException

        raise HTTPException(404, "用户组不存在")
    members = await UserGroupService.get_members(db, group_id)
    rgs = await UserGroupService.get_resource_groups(db, group_id)
    return {
        "id": group.id,
        "name": group.name,
        "name_cn": group.name_cn,
        "description": group.description,
        "leader_id": group.leader_id,
        "parent_id": group.parent_id,
        "is_active": group.is_active,
        "tenant_id": group.tenant_id,
        "member_ids": [m.id for m in members],
        "resource_group_ids": [rg.id for rg in rgs],
    }


@router.put("/user-groups/{group_id}/", summary="更新用户组")
async def update_user_group(
    group_id: int,
    data: UserGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    group = await UserGroupService.update_group(
        db,
        group_id,
        name_cn=data.name_cn,
        description=data.description,
        leader_id=data.leader_id,
        parent_id=data.parent_id,
        is_active=data.is_active,
        resource_group_ids=data.resource_group_ids,
        member_ids=data.member_ids,
    )
    return {"status": 0, "msg": "用户组已更新", "data": {"id": group.id}}


@router.delete("/user-groups/{group_id}/", summary="删除用户组")
async def delete_user_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    await UserGroupService.delete_group(db, group_id)
    return {"status": 0, "msg": "用户组已删除"}


@router.get("/user-groups/{group_id}/members/", summary="用户组成员列表")
async def list_group_members(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    members = await UserGroupService.get_members(db, group_id)
    return {
        "items": [
            {"id": m.id, "username": m.username, "display_name": m.display_name, "email": m.email}
            for m in members
        ]
    }


@router.get("/user-groups/{group_id}/resource-groups/", summary="用户组关联的资源组")
async def list_group_resource_groups(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    rgs = await UserGroupService.get_resource_groups(db, group_id)
    return {
        "items": [
            {"id": rg.id, "group_name": rg.group_name, "group_name_cn": rg.group_name_cn}
            for rg in rgs
        ]
    }
