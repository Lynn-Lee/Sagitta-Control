"""系统管理子路由。"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.models.system import DeliveryAcceptanceRun, DiagnosticBundle
from app.services.audit_log import AuditLogService
from app.services.commercial_ops import CommercialOpsService

from .schemas import AcceptanceRunRequest, RetentionCleanupRequest, RetentionPolicyUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 商业化实施、交付验收、诊断包和支持矩阵
# ═══════════════════════════════════════════════════════════


@router.get("/onboarding/status", summary="实施交付向导状态")
async def onboarding_status(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await CommercialOpsService.onboarding_status(db)


@router.post("/onboarding/steps/{step}/complete", summary="完成实施交付向导步骤")
async def complete_onboarding_step(
    step: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    try:
        data = await CommercialOpsService.complete_onboarding_step(db, step)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await AuditLogService.write(
        db,
        user,
        action="complete_onboarding_step",
        module="delivery",
        detail=f"完成实施步骤：{step}",
        request=request,
    )
    return data


@router.post("/onboarding/trial-bootstrap", summary="一键初始化商业试用环境")
async def bootstrap_trial_environment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    result = await CommercialOpsService.bootstrap_trial_environment(db, user)
    created_count = len(result.get("created") or [])
    updated_count = len(result.get("updated") or [])
    await AuditLogService.write(
        db,
        user,
        action="bootstrap_trial_environment",
        module="delivery",
        detail=f"初始化商业试用环境：新增 {created_count} 项，更新 {updated_count} 项",
        request=request,
    )
    return result


@router.post("/delivery/acceptance-runs", summary="创建商业交付验收报告")
async def create_acceptance_run(
    data: AcceptanceRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    run = await CommercialOpsService.create_acceptance_run(
        db,
        user,
        {"instance_id": data.instance_id, "db_name": data.db_name},
    )
    await AuditLogService.write(
        db,
        user,
        action="create_acceptance_run",
        module="delivery",
        detail=f"生成验收报告 #{run.id}",
        request=request,
    )
    return CommercialOpsService.run_to_dict(run)


@router.get("/delivery/acceptance-runs/{run_id}", summary="查看商业交付验收记录")
async def get_acceptance_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    run = (
        await db.execute(select(DeliveryAcceptanceRun).where(DeliveryAcceptanceRun.id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="验收记录不存在")
    return CommercialOpsService.run_to_dict(run)


@router.get("/delivery/acceptance-runs/{run_id}/report.md", summary="下载 Markdown 验收报告")
async def download_acceptance_markdown(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    run = (
        await db.execute(select(DeliveryAcceptanceRun).where(DeliveryAcceptanceRun.id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="验收记录不存在")
    content = (run.report_markdown or "").encode("utf-8")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'acceptance-run-{run_id}.md')}"
    }
    return StreamingResponse(iter([content]), media_type="text/markdown; charset=utf-8", headers=headers)


@router.get("/delivery/acceptance-runs/{run_id}/report.json", summary="下载 JSON 验收报告")
async def download_acceptance_json(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    import json

    run = (
        await db.execute(select(DeliveryAcceptanceRun).where(DeliveryAcceptanceRun.id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="验收记录不存在")
    content = json.dumps(run.report_json or {}, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'acceptance-run-{run_id}.json')}"
    }
    return StreamingResponse(iter([content]), media_type="application/json; charset=utf-8", headers=headers)


@router.post("/delivery/diagnostic-bundles", summary="生成商业支持诊断包")
async def create_diagnostic_bundle(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    bundle = await CommercialOpsService.create_diagnostic_bundle(db, user)
    await AuditLogService.write(
        db,
        user,
        action="create_diagnostic_bundle",
        module="delivery",
        detail=f"生成诊断包 #{bundle.id}",
        request=request,
    )
    return {
        "id": bundle.id,
        "status": bundle.status,
        "created_by": bundle.created_by,
        "created_at": bundle.created_at.isoformat() if bundle.created_at else "",
    }


@router.get("/delivery/diagnostic-bundles/{bundle_id}/download", summary="下载商业支持诊断包")
async def download_diagnostic_bundle(
    bundle_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    import json

    bundle = (
        await db.execute(select(DiagnosticBundle).where(DiagnosticBundle.id == bundle_id))
    ).scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="诊断包不存在")
    content = json.dumps(bundle.bundle_json or {}, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'diagnostic-bundle-{bundle_id}.json')}"
    }
    return StreamingResponse(iter([content]), media_type="application/json; charset=utf-8", headers=headers)


@router.get("/support/engine-matrix", summary="数据库引擎支持矩阵")
async def engine_support_matrix(_user=Depends(current_user)):
    return CommercialOpsService.engine_matrix()


@router.get("/support/about", summary="商业支持与关于信息")
async def support_about(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await CommercialOpsService.support_about(db)


@router.get("/compliance/reports/{report_type}", summary="合规报表")
async def compliance_report(
    report_type: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("audit_user")),
):
    try:
        return await CommercialOpsService.compliance_report(db, report_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/compliance/retention-policy", summary="审计合规保留策略")
async def retention_policy(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_perm("system_config_manage")),
):
    return await CommercialOpsService.retention_policy(db)


@router.put("/compliance/retention-policy", summary="更新审计合规保留策略")
async def update_retention_policy(
    data: RetentionPolicyUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    result = await CommercialOpsService.update_retention_policy(db, data.values)
    await AuditLogService.write(
        db,
        user,
        action="update_retention_policy",
        module="compliance",
        detail=f"更新保留策略：{data.values}",
        request=request,
    )
    return result


@router.post("/compliance/retention-policy/cleanup", summary="手动清理过期合规数据")
async def cleanup_retention_policy(
    data: RetentionCleanupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_perm("system_config_manage")),
):
    try:
        result = await CommercialOpsService.cleanup_retention_category(db, data.category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await AuditLogService.write(
        db,
        user,
        action="cleanup_retention_policy",
        module="compliance",
        detail=f"手动清理 {result['label']}，删除 {result['deleted']} 条",
        request=request,
    )
    return result
