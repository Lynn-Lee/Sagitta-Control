"""系统管理子路由。"""

from typing import Any
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_superuser, current_user
from app.services.audit_log import AuditLogService
from app.services.license import LicenseService

from .schemas import LicenseActivateRequest, LicenseChallengeRequest, LicenseImportRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 正式授权
# ═══════════════════════════════════════════════════════════


@router.get("/license/status", summary="License 授权状态")
async def get_license_status(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    return await LicenseService.status(db)


@router.get("/license/deployment-fingerprint", summary="预览正式激活部署指纹")
async def get_license_deployment_fingerprint(
    customer_id: str = Query("", max_length=128),
    customer_id_legacy: str = Query("", max_length=128, alias="customerId"),
    _user: dict[str, Any]=Depends(current_superuser),
) -> dict[str, Any]:
    return LicenseService.activation_fingerprint(customer_id or customer_id_legacy)


@router.post("/license/import", summary="导入离线 License")
async def import_license(
    data: LicenseImportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_superuser),
) -> dict[str, Any]:
    status_data = await LicenseService.import_license(db, data.license)
    await AuditLogService.write(
        db,
        user,
        action="import_license",
        module="system",
        detail=f"导入 License：{status_data.get('license_id') or '-'}",
        request=request,
    )
    return {"status": 0, "msg": "License 导入成功", "data": status_data}


@router.post("/license/challenge", summary="生成离线授权 Challenge")
async def create_license_challenge(
    data: LicenseChallengeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_superuser),
) -> dict[str, Any]:
    challenge = LicenseService.create_offline_challenge(data.customer_id)
    await AuditLogService.write(
        db,
        user,
        action="create_license_challenge",
        module="system",
        detail=f"生成离线 License Challenge：{challenge['payload'].get('customer_id') or '-'}",
        request=request,
    )
    return {"status": 0, "msg": "License Challenge 生成成功", "data": challenge}


@router.post("/license/activate", summary="在线激活 License")
async def activate_license(
    data: LicenseActivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_superuser),
) -> dict[str, Any]:
    status_data = await LicenseService.activate(db, data.model_dump())
    await AuditLogService.write(
        db,
        user,
        action="activate_license",
        module="system",
        detail=f"在线激活 License：{status_data.get('license_id') or '-'}",
        request=request,
    )
    return {"status": 0, "msg": "License 激活成功", "data": status_data}


@router.post("/license/refresh", summary="在线续期 License")
async def refresh_license(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_superuser),
) -> dict[str, Any]:
    status_data = await LicenseService.refresh(db)
    await AuditLogService.write(
        db,
        user,
        action="refresh_license",
        module="system",
        detail=f"刷新 License：{status_data.get('license_id') or '-'}",
        request=request,
    )
    return {"status": 0, "msg": "License 刷新成功", "data": status_data}
