"""系统管理子路由。"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_perm
from app.services.audit_log import AuditLogService
from app.services.commercial_ops import CommercialOpsService
from app.services.role import RoleService
from app.services.user import UserService

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 审计日志
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


@router.get("/audit-logs/export", summary="导出操作审计日志")
async def export_audit_logs(
    username: str | None = None,
    module: str | None = None,
    action: str | None = None,
    result: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    export_format: str = Query("xlsx", pattern="^(xlsx|csv|json)$"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("audit_user")),
):
    _total, logs = await AuditLogService.list_logs(
        db,
        username=username,
        module=module,
        action=action,
        result=result,
        date_start=date_start,
        date_end=date_end,
        page=1,
        page_size=10000,
    )
    rows = [
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
    ]
    content, media_type, filename = CommercialOpsService.build_rows_file(
        rows, export_format, "audit_logs"
    )
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(iter([content]), media_type=media_type, headers=headers)


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
