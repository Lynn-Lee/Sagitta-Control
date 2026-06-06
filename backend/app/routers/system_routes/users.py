"""系统管理子路由。"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_perm
from app.schemas.user import (
    GrantPermissionRequest,
    UserCreate,
    UserUpdate,
)
from app.services.license import LicenseService
from app.services.user import UserService

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
                "dingtalk_user_id": u.dingtalk_user_id,
                "feishu_open_id": u.feishu_open_id,
                "wecom_userid": u.wecom_userid,
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
    await LicenseService.enforce_max_users(db)
    user = await UserService.create_user(db, data)
    return {"status": 0, "msg": "用户创建成功", "data": {"id": user.id, "username": user.username}}


@router.get("/users/{user_id}/", summary="用户详情")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("user_manage")),
):

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
        "dingtalk_user_id": user.dingtalk_user_id,
        "feishu_open_id": user.feishu_open_id,
        "wecom_userid": user.wecom_userid,
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
