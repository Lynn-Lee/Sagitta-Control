"""可观测中心路由（Sprint 5）。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as QParam
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.monitor import (
    AuditMonitorPrivRequest,
    MonitorConfigCreate,
    MonitorConfigUpdate,
    MonitorPrivApplyRequest,
)
from app.services.monitor import DashboardService, MonitorService

logger = logging.getLogger(__name__)
router = APIRouter()
sd_router = APIRouter()


# ── Dashboard 统计 ────────────────────────────────────────────

@router.get("/dashboard/stats/", summary="Dashboard 首页统计")
async def dashboard_stats(
    days: int = QParam(30, ge=1, le=365, description="统计周期（天），默认30天，用户可自定义"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_stats(db, days=days)


@router.get("/dashboard/workflow-trend/", summary="工单趋势（支持自定义天数）")
async def workflow_trend(
    days: int = QParam(7, ge=1, le=90, description="展示最近 N 天，默认7天，最多90天"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await DashboardService.get_workflow_trend(db, days)}


@router.get("/dashboard/instance-dist/", summary="实例类型分布")
async def instance_dist(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await DashboardService.get_instance_dist(db)}


@router.get("/dashboard/query-overview/", summary="在线查询概览")
async def query_overview(
    days: int = QParam(7, ge=1, le=365, description="展示最近 N 天，默认7天"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_query_overview(db, user=user, days=days)


@router.get("/dashboard/workflow-overview/", summary="SQL 工单概览")
async def workflow_overview(
    days: int = QParam(7, ge=1, le=365, description="展示最近 N 天，默认7天"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_workflow_overview(db, user=user, days=days)


@router.get("/dashboard/archive-overview/", summary="数据归档概览")
async def archive_overview(
    days: int = QParam(7, ge=1, le=365, description="展示最近 N 天，默认7天"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_archive_overview(db, user=user, days=days)


@router.get("/dashboard/instance-overview/", summary="实例与库概览")
async def instance_overview(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_instance_overview(db, user=user)


# ── 采集配置 ──────────────────────────────────────────────────

@router.get("/configs/", summary="采集配置列表", dependencies=[Depends(require_perm("monitor_config_manage"))])
async def list_configs(
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await MonitorService.list_configs(db, user, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/configs/", summary="新建采集配置", dependencies=[Depends(require_perm("monitor_config_manage"))])
async def create_config(
    data: MonitorConfigCreate,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await MonitorService.create_config(db, data, user)
    return {"status": 0, "msg": "采集配置创建成功", "data": {"id": cfg.id}}


@router.put("/configs/{config_id}/", summary="更新采集配置", dependencies=[Depends(require_perm("monitor_config_manage"))])
async def update_config(
    config_id: int,
    data: MonitorConfigUpdate,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await MonitorService.update_config_with_access(db, config_id, data, user)
    return {"status": 0, "msg": "采集配置已更新", "data": {"id": cfg.id}}


@router.delete("/configs/{config_id}/", summary="删除采集配置", dependencies=[Depends(require_perm("monitor_config_manage"))])
async def delete_config(
    config_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await MonitorService.delete_config(db, config_id, user)
    return {"status": 0, "msg": "采集配置已删除"}


# ── 监控权限申请 ──────────────────────────────────────────────

@router.post("/privileges/apply/", summary="申请监控权限")
async def apply_privilege(
    data: MonitorPrivApplyRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    apply = await MonitorService.apply_privilege(db, data, user)
    return {"status": 0, "msg": "申请已提交", "data": {"apply_id": apply.id}}


@router.get("/privileges/applies/", summary="权限申请列表")
async def list_applies(
    status: int | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, applies = await MonitorService.list_applies(db, user, status, page, page_size)
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [
            {
                "id": a.id, "title": a.title, "instance_id": a.instance_id,
                "valid_date": a.valid_date.isoformat(), "status": a.status,
                "apply_reason": a.apply_reason,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            }
            for a in applies
        ],
    }


@router.post("/privileges/audit/", summary="审批监控权限", dependencies=[Depends(require_perm("monitor_review"))])
async def audit_privilege(
    apply_id: int,
    data: AuditMonitorPrivRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    apply = await MonitorService.audit_privilege(db, apply_id, data.action, user, data.remark)
    return {"status": 0, "msg": "审批完成", "data": {"apply_id": apply.id, "status": apply.status}}


# ── 实例指标（代理到 Prometheus）─────────────────────────────

@router.get("/instances/{instance_id}/metrics/", summary="实例指标概览")
async def instance_metrics(
    instance_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    has_priv = await MonitorService.check_privilege(db, user, instance_id)
    if not has_priv:
        raise HTTPException(403, "没有该实例的监控查看权限")

    # 从引擎层获取实时指标
    from sqlalchemy import select

    from app.engines.registry import get_engine
    from app.models.instance import Instance
    inst_result = await db.execute(select(Instance).where(Instance.id == instance_id))
    inst = inst_result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "实例不存在")

    engine = get_engine(inst)
    metrics = await engine.collect_metrics()
    return {"instance_id": instance_id, "metrics": metrics}


# ── Prometheus HTTP SD 端点（内部，不鉴权）────────────────────

@sd_router.get("/prometheus/sd-targets", summary="Prometheus HTTP SD 发现目标", include_in_schema=False)
async def prometheus_sd_targets(db: AsyncSession = Depends(get_db)):
    """
    Prometheus HTTP SD 端点。
    在 prometheus.yml 中配置：
      - job_name: sagittadb_sd
        http_sd_configs:
          - url: http://backend:8000/internal/prometheus/sd-targets
            refresh_interval: 60s
    此端点只允许内网访问（在 nginx.conf 中已限制 allow 10.0.0.0/8 等）。
    """
    targets = await MonitorService.get_sd_targets(db)
    return JSONResponse(content=targets)
