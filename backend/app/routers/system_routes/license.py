"""系统管理子路由。"""

from typing import Any
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_superuser, current_user
from app.services.audit_log import AuditLogService
from app.services.license import LicenseService

from .schemas import (
    LicenseActivateRequest,
    LicenseChallengeRequest,
    LicenseImportRequest,
    LicenseInstanceSelectionRequest,
    LicenseTrialCodeRequest,
    LicenseTrialRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 用户授权
# ═══════════════════════════════════════════════════════════


@router.get("/license/status", summary="License 授权状态")
async def get_license_status(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    return await LicenseService.status(db)


@router.get("/license/deployment-fingerprint", summary="预览用户授权部署指纹")
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


@router.get("/license/instance-allocation", summary="实例额度分配")
async def get_instance_allocation(
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(current_superuser),
) -> dict[str, Any]:
    return await LicenseService.instance_allocation(db)


@router.put("/license/instance-allocation", summary="指定额度内启用的实例")
async def update_instance_allocation(
    data: LicenseInstanceSelectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(current_superuser),
) -> dict[str, Any]:
    result = await LicenseService.select_active_instances(db, data.instance_ids)
    await AuditLogService.write(
        db,
        user,
        action="update_license_instance_allocation",
        module="system",
        detail=f"调整额度内启用实例：{len(data.instance_ids)} 个",
        request=request,
    )
    return {"status": 0, "msg": "实例额度已更新", "data": result}


@router.post("/license/trial/send-code", summary="发送试用登记邮箱验证码")
async def send_trial_code(
    data: LicenseTrialCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(current_superuser),
) -> dict[str, Any]:
    result = await LicenseService.send_trial_code(db, data.model_dump())
    return {"status": 0, "msg": "验证码已发送", "data": result}


@router.post("/license/trial", summary="登记并领取完整试用授权")
async def request_trial_license(
    data: LicenseTrialRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(current_superuser),
) -> dict[str, Any]:
    status_data = await LicenseService.request_trial(db, data.model_dump())
    await AuditLogService.write(
        db,
        user,
        action="request_trial_license",
        module="system",
        detail=f"登记试用授权：{data.company_name or '-'}",
        request=request,
    )
    return {"status": 0, "msg": "试用授权已开通", "data": status_data}


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
