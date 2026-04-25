"""Slow query analysis routes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as QParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.schemas.slowlog import (
    SlowQueryCollectResponse,
    SlowQueryConfigListResponse,
    SlowQueryConfigUpdate,
    SlowQueryConfigUpsert,
    SlowQueryExplainRequest,
    SlowQueryExplainResponse,
    SlowQueryFingerprintDetailResponse,
    SlowQueryFingerprintListResponse,
    SlowQueryLogListResponse,
    SlowQueryOverviewResponse,
)
from app.services.slowlog import DEFAULT_SLOW_THRESHOLD_MS, SlowLogService

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "时间格式错误，请使用 ISO8601") from None


@router.get("/configs/", response_model=SlowQueryConfigListResponse, summary="慢日志采集配置列表")
async def list_slowlog_configs(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await SlowLogService.list_configs(db, user)
    return {"total": total, "items": items}


@router.post("/configs/", summary="创建或更新慢日志采集配置", dependencies=[Depends(require_perm("menu_ops"))])
async def upsert_slowlog_config(
    data: SlowQueryConfigUpsert,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await SlowLogService.upsert_config(db, data, user)
    return {"status": 0, "msg": "慢日志采集配置已保存", "data": {"id": cfg.id}}


@router.put("/configs/{config_id}/", summary="更新慢日志采集配置", dependencies=[Depends(require_perm("menu_ops"))])
async def update_slowlog_config(
    config_id: int,
    data: SlowQueryConfigUpdate,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await SlowLogService.update_config(db, config_id, data, user)
    return {"status": 0, "msg": "慢日志采集配置已更新", "data": {"id": cfg.id}}


@router.get("/logs/", response_model=SlowQueryLogListResponse, summary="慢 SQL 明细列表")
async def list_slow_logs(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(50, ge=1, le=200),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await SlowLogService.list_logs(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/overview/", response_model=SlowQueryOverviewResponse, summary="慢 SQL 总览")
async def slowlog_overview(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SlowLogService.overview(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
    )


@router.get("/fingerprints/", response_model=SlowQueryFingerprintListResponse, summary="慢 SQL 指纹聚合")
async def slowlog_fingerprints(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await SlowLogService.fingerprints(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        limit=limit,
    )
    return {"total": len(items), "items": items}


@router.get("/fingerprints/{fingerprint}/samples/", summary="慢 SQL 指纹样例")
async def slowlog_fingerprint_samples(
    fingerprint: str,
    limit: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await SlowLogService.samples(db, user, fingerprint, limit=limit)}


@router.get(
    "/fingerprints/{fingerprint}/detail/",
    response_model=SlowQueryFingerprintDetailResponse,
    summary="慢 SQL 指纹详情",
)
async def slowlog_fingerprint_detail(
    fingerprint: str,
    date_start: str | None = None,
    date_end: str | None = None,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SlowLogService.fingerprint_detail(
        db,
        user,
        fingerprint,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
    )


@router.post(
    "/explain/",
    response_model=SlowQueryExplainResponse,
    summary="慢 SQL 执行计划分析",
)
async def explain_slow_query(
    data: SlowQueryExplainRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await SlowLogService.explain(
        db,
        user,
        log_id=data.log_id,
        instance_id=data.instance_id,
        db_name=data.db_name,
        sql=data.sql,
    )


@router.post("/collect/", response_model=SlowQueryCollectResponse, summary="手动触发慢日志采集")
async def collect_slow_logs(
    instance_id: int | None = None,
    limit: int = QParam(100, ge=1, le=500),
    user: dict = Depends(require_perm("menu_ops")),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(UTC) - timedelta(days=1)
    saved = 0
    failed = 0
    unsupported = 0
    errors: list[str] = []

    if instance_id:
        instances = [await SlowLogService.get_instance_or_404(db, instance_id, user)]
    else:
        result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.is_active.is_(True))
        )
        instances = [inst for inst in result.scalars().all() if SlowLogService.can_access_instance(user, inst)]

    for inst in instances:
        try:
            cfg = await SlowLogService.ensure_default_config(db, inst, user)
            if cfg.is_enabled:
                saved += await SlowLogService.sync_platform_logs(
                    db,
                    threshold_ms=cfg.threshold_ms,
                    since=since,
                    instance_id=inst.id,
                )
            count, err = await SlowLogService.collect_instance(db, inst, limit=limit, since=since, config=cfg)
            saved += count
            if err:
                if "暂不支持" in err:
                    unsupported += 1
                else:
                    failed += 1
                errors.append(f"{inst.instance_name}: {err}")
        except Exception as exc:
            failed += 1
            logger.warning("slowlog_collect_failed instance_id=%s error=%s", inst.id, exc)
            errors.append(f"{inst.instance_name}: {exc}")

    return {
        "instances": len(instances),
        "saved": saved,
        "failed": failed,
        "unsupported": unsupported,
        "msg": "采集完成",
        "errors": errors[:20],
    }


@router.get("/", summary="实时慢查询列表")
async def list_slow_queries(
    instance_id: int = QParam(...),
    db_name: str | None = None,
    limit: int = QParam(50, ge=1, le=500),
    min_seconds: int = QParam(1, ge=1),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await SlowLogService.get_instance_or_404(db, instance_id, user)
    engine = get_engine(inst)

    if inst.db_type == "pgsql":
        sql = """
            SELECT pid, usename, datname, state,
                   extract(epoch from (now()-query_start))::int AS duration_seconds,
                   query
            FROM pg_stat_activity
            WHERE state != 'idle'
              AND query_start < now() - ($2::text || ' seconds')::interval
              AND pid != pg_backend_pid()
            ORDER BY duration_seconds DESC
            LIMIT $1
        """
        rs = await engine._raw_query(db_name=db_name or inst.db_name, sql=sql, args=[limit, min_seconds])
    elif inst.db_type == "mysql":
        sql = (
            "SELECT Id, User, Host, db, Command, Time, State, LEFT(Info,200) AS Info "
            "FROM information_schema.PROCESSLIST "
            "WHERE Command != 'Sleep' AND Time > %(min_seconds)s "
            "ORDER BY Time DESC LIMIT %(limit)s"
        )
        rs = await engine.query(
            db_name="information_schema",
            sql=sql,
            parameters={"min_seconds": min_seconds, "limit": limit},
            limit_num=limit,
        )
    elif inst.db_type == "starrocks":
        rs = await engine.processlist(command_type="ALL")
        if rs.is_success:
            rs.rows = [
                row for row in rs.rows
                if int((row.get("Time", row.get("TIME", 0)) if isinstance(row, dict) else 0) or 0) > min_seconds
            ][:limit]
    else:
        return {"items": [], "total": 0, "msg": f"{inst.db_type} 暂不支持实时慢查询分析"}

    if rs.error:
        raise HTTPException(400, f"查询慢日志失败：{rs.error}")
    cols = rs.column_list or []
    return {
        "items": [dict(zip(cols, r, strict=False)) if isinstance(r, tuple) else r for r in rs.rows],
        "total": len(rs.rows),
    }


@router.get("/stats/", summary="慢查询统计（兼容旧接口）")
async def slow_query_stats(
    instance_id: int = QParam(...),
    limit: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await SlowLogService.get_instance_or_404(db, instance_id, user)
    items = await SlowLogService.fingerprints(db, user, instance_id=instance_id, limit=limit)
    return {"items": [item.model_dump() for item in items]}
