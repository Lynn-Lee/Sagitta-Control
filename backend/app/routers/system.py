"""系统管理路由：用户、角色、用户组、资源组、权限、系统配置、审计日志（v2 授权体系）。"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
    UserGroupCreate,
    UserGroupUpdate,
)
from app.schemas.user import (
    GrantPermissionRequest,
    ResourceGroupCreate,
    ResourceGroupUpdate,
    UserCreate,
    UserUpdate,
)
from app.services.audit_log import AuditLogService
from app.services.role import RoleService, UserGroupService
from app.services.system_config import SystemConfigService
from app.services.user import ResourceGroupService, UserService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 用户管理
# ═══════════════════════════════════════════════════════════


@router.get("/users/", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    is_active: bool | None = None,
    role_ids: list[int] | None = Query(None),
    user_group_ids: list[int] | None = Query(None),
    departments: list[str] | None = Query(None),
    titles: list[str] | None = Query(None),
    statuses: list[bool] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    total, items = await UserService.list_users(
        db,
        page,
        page_size,
        search,
        is_active,
        role_ids=role_ids,
        user_group_ids=user_group_ids,
        departments=departments,
        titles=titles,
        statuses=statuses,
    )
    perms_map = {u.id: await UserService.get_merged_permissions(db, u.id, u) for u in items}
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "email": u.email,
                "phone": u.phone,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "auth_type": u.auth_type,
                "totp_enabled": u.totp_enabled,
                "user_groups": [
                    {"id": ug.id, "name": ug.name, "name_cn": ug.name_cn} for ug in u.user_groups
                ],
                "role_id": u.role_id,
                "role_name": u.role.name_cn
                if u.role and u.role.name_cn
                else (u.role.name if u.role else None),
                "manager_id": u.manager_id,
                "manager_username": u.manager.username if u.manager else "",
                "manager_display_name": u.manager.display_name if u.manager else "",
                "employee_id": u.employee_id,
                "department": u.department,
                "title": u.title,
                "permissions": perms_map.get(u.id, []),
                "tenant_id": u.tenant_id,
            }
            for u in items
        ],
    }


@router.get("/users/export/", summary="导出用户")
async def export_users(
    export_format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    search: str | None = None,
    is_active: bool | None = None,
    role_ids: list[int] | None = Query(None),
    user_group_ids: list[int] | None = Query(None),
    departments: list[str] | None = Query(None),
    titles: list[str] | None = Query(None),
    statuses: list[bool] | None = Query(None),
    user_ids: list[int] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    rows = await UserService.export_users(
        db,
        search=search,
        is_active=is_active,
        role_ids=role_ids,
        user_group_ids=user_group_ids,
        departments=departments,
        titles=titles,
        statuses=statuses,
        user_ids=user_ids,
    )
    content, media_type, filename = UserService.build_user_export_file(rows, export_format)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


@router.get("/users/import-template/", summary="下载用户导入模板")
async def download_user_import_template(
    export_format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    _user=Depends(require_perm("user_manage")),
):
    content, media_type, filename = UserService.build_user_import_template(export_format)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


@router.post("/users/import/", summary="导入用户")
async def import_users(
    file: UploadFile = File(...),
    default_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    result = await UserService.import_users(
        db=db,
        filename=file.filename or "",
        content=await file.read(),
        default_password=default_password,
    )
    return {"status": 0, "msg": "用户导入完成", "data": result}


@router.post("/users/", summary="创建用户")
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    user = await UserService.create_user(db, data)
    return {"status": 0, "msg": "用户创建成功", "data": {"id": user.id, "username": user.username}}


@router.get("/users/{user_id}/", summary="用户详情")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    from fastapi import HTTPException

    user = await UserService.get_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    permissions = await UserService.get_merged_permissions(db, user.id, user)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "auth_type": user.auth_type,
        "totp_enabled": user.totp_enabled,
        "role_id": user.role_id,
        "manager_id": user.manager_id,
        "employee_id": user.employee_id,
        "department": user.department,
        "title": user.title,
        "user_groups": [
            {"id": ug.id, "name": ug.name, "name_cn": ug.name_cn} for ug in user.user_groups
        ],
        "permissions": permissions,
        "tenant_id": user.tenant_id,
    }


@router.put("/users/{user_id}/", summary="更新用户")
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    user = await UserService.update_user(db, user_id, data)
    return {"status": 0, "msg": "用户已更新", "data": {"id": user.id}}


@router.delete("/users/{user_id}/", summary="删除用户")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    await UserService.delete_user(db, user_id)
    return {"status": 0, "msg": "用户已删除"}


@router.post("/users/{user_id}/permissions/grant/", summary="授予权限")
async def grant_permissions(
    user_id: int,
    data: GrantPermissionRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    await UserService.grant_permissions(db, user_id, data.permission_codes)
    return {"status": 0, "msg": f"已授予 {len(data.permission_codes)} 个权限"}


@router.post("/users/{user_id}/permissions/revoke/", summary="撤销权限")
async def revoke_permissions(
    user_id: int,
    data: GrantPermissionRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    await UserService.revoke_permissions(db, user_id, data.permission_codes)
    return {"status": 0, "msg": f"已撤销 {len(data.permission_codes)} 个权限"}


# ═══════════════════════════════════════════════════════════
# 角色管理
# ═══════════════════════════════════════════════════════════


@router.get("/roles/", summary="角色列表")
async def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    total, items = await RoleService.list_roles(db, page, page_size, is_active)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "name_cn": r.name_cn,
                "description": r.description,
                "is_system": r.is_system,
                "is_active": r.is_active,
                "tenant_id": r.tenant_id,
                "permissions": [p.codename for p in r.permissions],
            }
            for r in items
        ],
    }


@router.post("/roles/", summary="创建角色")
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    role = await RoleService.create_role(
        db,
        name=data.name,
        name_cn=data.name_cn,
        description=data.description,
        permission_codes=data.permission_codes,
    )
    return {"status": 0, "msg": "角色创建成功", "data": {"id": role.id, "name": role.name}}


@router.get("/roles/{role_id}/", summary="角色详情")
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    role = await RoleService.get_by_id(db, role_id)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(404, "角色不存在")
    return {
        "id": role.id,
        "name": role.name,
        "name_cn": role.name_cn,
        "description": role.description,
        "is_system": role.is_system,
        "is_active": role.is_active,
        "tenant_id": role.tenant_id,
        "permissions": [p.codename for p in role.permissions],
    }


@router.put("/roles/{role_id}/", summary="更新角色")
async def update_role(
    role_id: int,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    role = await RoleService.update_role(
        db,
        role_id,
        name_cn=data.name_cn,
        description=data.description,
        is_active=data.is_active,
        permission_codes=data.permission_codes,
    )
    return {"status": 0, "msg": "角色已更新", "data": {"id": role.id}}


@router.delete("/roles/{role_id}/", summary="删除角色")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
    await RoleService.delete_role(db, role_id)
    return {"status": 0, "msg": "角色已删除"}


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
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
    content, media_type, filename = UserGroupService.build_group_import_template(export_format)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


@router.post("/user-groups/import/", summary="导入用户组")
async def import_user_groups(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
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
    _user=Depends(require_perm("user_manage")),
):
    await UserGroupService.delete_group(db, group_id)
    return {"status": 0, "msg": "用户组已删除"}


@router.get("/user-groups/{group_id}/members/", summary="用户组成员列表")
async def list_group_members(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(current_user),
):
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
    _user=Depends(current_user),
):
    rgs = await UserGroupService.get_resource_groups(db, group_id)
    return {
        "items": [
            {"id": rg.id, "group_name": rg.group_name, "group_name_cn": rg.group_name_cn}
            for rg in rgs
        ]
    }


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
    from sqlalchemy import select

    from app.models.role import group_resource_group, user_group_member
    from app.models.user import Users

    result = await db.execute(
        select(Users)
        .join(user_group_member, Users.id == user_group_member.c.user_id)
        .join(
            group_resource_group,
            user_group_member.c.group_id == group_resource_group.c.group_id,
        )
        .where(group_resource_group.c.resource_group_id == rg_id)
        .distinct()
    )
    members = result.scalars().all()
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
    from sqlalchemy import delete, select

    from app.models.role import group_resource_group
    from app.models.user import ResourceGroup

    rg_result = await db.execute(select(ResourceGroup).where(ResourceGroup.id == rg_id))
    rg = rg_result.scalar_one_or_none()
    if not rg:
        from fastapi import HTTPException

        raise HTTPException(404, "资源组不存在")

    await db.execute(
        delete(group_resource_group).where(group_resource_group.c.resource_group_id == rg_id)
    )
    for gid in data.user_group_ids:
        await db.execute(
            group_resource_group.insert().values(group_id=gid, resource_group_id=rg_id)
        )
    await db.commit()
    return {"status": 0, "msg": f"资源组用户组关联已更新，共 {len(data.user_group_ids)} 个组"}


# ═══════════════════════════════════════════════════════════
# 权限码
# ═══════════════════════════════════════════════════════════


@router.get("/permissions/", summary="权限码列表")
async def list_permissions(db: AsyncSession = Depends(get_db), _user=Depends(current_user)):
    from sqlalchemy import select

    from app.models.user import Permission

    result = await db.execute(select(Permission).order_by(Permission.codename))
    perms = result.scalars().all()
    return {"permissions": [{"codename": p.codename, "name": p.name} for p in perms]}


# ═══════════════════════════════════════════════════════════
# 系统配置（Pack C1 完整实现）
# ═══════════════════════════════════════════════════════════


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, str]


class MailTestRequest(BaseModel):
    to_email: str


class LdapTestRequest(BaseModel):
    test_username: str = ""
    test_password: str = ""


@router.get("/config/", summary="获取系统配置（按分组）")
async def get_system_config(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await SystemConfigService.get_all(db)


@router.post("/config/", summary="批量更新系统配置")
async def update_system_config(
    data: ConfigUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    count, change_summary = await SystemConfigService.update_batch(db, data.updates)
    # 审计日志记录具体变更项（敏感字段只记key，不记值）
    detail = (
        f"更新 {count} 个配置项：" + "；".join(change_summary)
        if change_summary
        else f"更新 {count} 个配置项"
    )
    await AuditLogService.write(
        db,
        user,
        action="update_config",
        module="system",
        detail=detail,
        request=request,
    )
    return {"status": 0, "msg": f"已保存 {count} 个配置项", "count": count}


@router.post("/config/test/mail/", summary="测试邮件配置")
async def test_mail_config(
    data: MailTestRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    result = await SystemConfigService.test_mail(db, data.to_email)
    return result


@router.post("/config/test/dingtalk/", summary="测试钉钉配置")
async def test_dingtalk_config(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await SystemConfigService.test_dingtalk(db)


@router.post("/config/test/wecom/", summary="测试企业微信配置")
async def test_wecom_config(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await SystemConfigService.test_wecom(db)


@router.post("/config/test/feishu/", summary="测试飞书配置")
async def test_feishu_config(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await SystemConfigService.test_feishu(db)


@router.post("/config/test/ldap/", summary="测试 LDAP 配置")
async def test_ldap_config(
    data: LdapTestRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await SystemConfigService.test_ldap(db, data.test_username, data.test_password)


# ═══════════════════════════════════════════════════════════
# 审计日志（Pack C1）
# ═══════════════════════════════════════════════════════════


@router.get("/audit-logs/", summary="操作审计日志列表")
async def list_audit_logs(
    username: str | None = None,
    module: str | None = None,
    action: str | None = None,
    result: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("audit_user")),
):
    total, logs = await AuditLogService.list_logs(
        db,
        username=username,
        module=module,
        action=action,
        result=result,
        date_start=date_start,
        date_end=date_end,
        page=page,
        page_size=page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": log.id,
                "username": log.username,
                "action": log.action,
                "module": log.module,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "result": log.result,
                "remark": log.remark,
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
            for log in logs
        ],
        "modules": AuditLogService.get_modules(),
    }


# ═══════════════════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════════════════


@router.post("/init/", summary="初始化系统", include_in_schema=False)
async def init_system(db: AsyncSession = Depends(get_db)):
    await RoleService.init_builtin_roles(db)
    existing = await UserService.get_by_username(db, "admin")
    if not existing:
        from app.schemas.user import UserCreate

        await UserService.create_user(
            db,
            UserCreate(
                username="admin",
                password="Admin@2024!",
                display_name="超级管理员",
                is_superuser=True,
            ),
        )
        return {
            "status": 0,
            "msg": "系统初始化完成，默认管理员：admin / Admin@2024！（请立即修改密码）\n已创建 4 个内置角色：superadmin / dba / dba_group / developer",
        }
    return {"status": 0, "msg": "系统已初始化，权限表与角色已更新"}
