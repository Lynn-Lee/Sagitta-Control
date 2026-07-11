"""系统访问控制子路由。"""

from typing import Any
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_perm
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
)
from app.services.role import RoleService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 角色管理
# ═══════════════════════════════════════════════════════════


@router.get("/roles/", summary="角色列表")
async def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
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
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
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
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
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
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
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
    _user: dict[str, Any]=Depends(require_perm("user_manage")),
) -> dict[str, Any]:
    await RoleService.delete_role(db, role_id)
    return {"status": 0, "msg": "角色已删除"}
