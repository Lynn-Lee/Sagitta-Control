"""慢 SQL 分析路由。"""

from __future__ import annotations

from typing import Any, cast

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
from app.services.slowlog import DEFAULT_SLOW_THRESHOLD_MS, SlowLogService, tag_options_by_engine

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "时间格式错误，请使用 ISO8601") from None


def _row_duration_seconds(row: Any) -> int:
    if not isinstance(row, dict):
        return 0
    for key in ("Time", "TIME", "time_seconds", "duration_seconds"):
        if key not in row:
            continue
        try:
            return int(float(row.get(key) or 0))
        except (TypeError, ValueError):
            continue
    duration_ms = row.get("duration_ms")
    try:
        return int(float(duration_ms or 0) / 1000)
    except (TypeError, ValueError):
        return 0


@router.get(
    "/configs/",
    response_model=SlowQueryConfigListResponse,
    summary="SQL 采集配置列表",
    dependencies=[Depends(require_perm("observability_collect_manage"))],
)
async def list_slowlog_configs(
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    total, items = await SlowLogService.list_configs(db, user)
    return {"total": total, "items": items}


@router.get("/tag-options/", summary="SQL 洞察标签选项")
async def slowlog_tag_options() -> dict[str, Any]:
    return {"items": tag_options_by_engine()}


@router.post(
    "/configs/",
    summary="创建或更新 SQL 采集配置",
    dependencies=[Depends(require_perm("observability_collect_manage"))],
)
async def upsert_slowlog_config(
    data: SlowQueryConfigUpsert,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cfg = await SlowLogService.upsert_config(db, data, user)
    return {"status": 0, "msg": "SQL 采集配置已保存", "data": {"id": cfg.id}}


@router.put(
    "/configs/{config_id}/",
    summary="更新 SQL 采集配置",
    dependencies=[Depends(require_perm("observability_collect_manage"))],
)
async def update_slowlog_config(
    config_id: int,
    data: SlowQueryConfigUpdate,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cfg = await SlowLogService.update_config(db, config_id, data, user)
    return {"status": 0, "msg": "SQL 采集配置已更新", "data": {"id": cfg.id}}


@router.get(
    "/logs/",
    response_model=SlowQueryLogListResponse,
    summary="SQL 样本列表",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def list_slow_logs(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    username: str | None = None,
    tag: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(50, ge=1, le=200),
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    total, items = await SlowLogService.list_logs(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        username=username,
        tag=tag,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get(
    "/overview/",
    response_model=SlowQueryOverviewResponse,
    summary="SQL 洞察总览",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def slowlog_overview(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    username: str | None = None,
    tag: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SlowQueryOverviewResponse:
    return await SlowLogService.overview(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        username=username,
        tag=tag,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
    )


@router.get(
    "/fingerprints/",
    response_model=SlowQueryFingerprintListResponse,
    summary="SQL 指纹聚合",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def slowlog_fingerprints(
    instance_id: int | None = None,
    db_name: str | None = None,
    source: str | None = None,
    username: str | None = None,
    tag: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int = QParam(DEFAULT_SLOW_THRESHOLD_MS, ge=0),
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = QParam(20, ge=1, le=100),
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    items = await SlowLogService.fingerprints(
        db,
        user,
        instance_id=instance_id,
        db_name=db_name,
        source=source,
        username=username,
        tag=tag,
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        limit=limit,
    )
    return {"total": len(items), "items": items}


@router.get(
    "/fingerprints/{fingerprint}/samples/",
    summary="SQL 指纹样例",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def slowlog_fingerprint_samples(
    fingerprint: str,
    limit: int = QParam(20, ge=1, le=100),
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return {"items": await SlowLogService.samples(db, user, fingerprint, limit=limit)}


@router.get(
    "/fingerprints/{fingerprint}/detail/",
    response_model=SlowQueryFingerprintDetailResponse,
    summary="SQL 指纹详情",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def slowlog_fingerprint_detail(
    fingerprint: str,
    date_start: str | None = None,
    date_end: str | None = None,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SlowQueryFingerprintDetailResponse:
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
    summary="SQL 执行计划分析",
    dependencies=[Depends(require_perm("observability_sql_analyze"))],
)
async def explain_slow_query(
    data: SlowQueryExplainRequest,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SlowQueryExplainResponse:
    return await SlowLogService.explain(
        db,
        user,
        log_id=data.log_id,
        instance_id=data.instance_id,
        db_name=data.db_name,
        sql=data.sql,
    )


@router.post("/collect/", response_model=SlowQueryCollectResponse, summary="手动触发 SQL 采集")
async def collect_slow_logs(
    instance_id: int | None = None,
    limit: int = QParam(100, ge=1, le=500),
    user: dict[str, Any] = Depends(require_perm("observability_collect_manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=1)
    saved = 0
    failed = 0
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
        inst_id = inst.id
        inst_name = inst.instance_name
        try:
            cfg = await SlowLogService.ensure_default_config(db, inst, user)
            count, err = await SlowLogService.collect_instance(db, inst, limit=limit, since=since, config=cfg)
            saved += count
            if err:
                failed += 1
                errors.append(f"{inst_name}: {err}")
        except Exception as exc:
            await db.rollback()
            failed += 1
            logger.warning("slowlog_collect_failed instance_id=%s error=%s", inst_id, exc)
            errors.append(f"{inst_name}: {exc}")

    return {
        "instances": len(instances),
        "saved": saved,
        "failed": failed,
        "unsupported": 0,
        "msg": "采集完成",
        "errors": errors[:20],
    }


@router.get(
    "/",
    summary="实时 SQL 列表",
    dependencies=[Depends(require_perm("observability_sql_view"))],
)
async def list_slow_queries(
    instance_id: int = QParam(...),
    db_name: str | None = None,
    limit: int = QParam(50, ge=1, le=500),
    min_seconds: int = QParam(1, ge=1),
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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
        rs = await cast(Any, engine)._raw_query(db_name=db_name or inst.db_name, sql=sql, args=[limit, min_seconds])
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
    elif inst.db_type in {"starrocks", "doris"}:
        rs = await engine.processlist(command_type="ALL")
        if rs.is_success:
            rs.rows = [
                row for row in rs.rows
                if _row_duration_seconds(row) > min_seconds
            ][:limit]
    elif inst.db_type == "oracle" and hasattr(engine, "collect_sql_activity"):
        rs = await engine.collect_sql_activity(
            limit=limit,
            min_duration_ms=min_seconds * 1000,
        )
    else:
        return {"items": [], "total": 0, "msg": f"{inst.db_type} 暂不支持实时 SQL 洞察"}

    if rs.error:
        raise HTTPException(400, f"查询实时 SQL 失败：{rs.error}")
    cols = rs.column_list or []
    return {
        "items": [dict(zip(cols, r, strict=False)) if isinstance(r, tuple) else r for r in rs.rows],
        "total": len(rs.rows),
        "warning": getattr(rs, "warning", ""),
    }


@router.get("/stats/", summary="慢查询统计（兼容旧接口）")
async def slow_query_stats(
    instance_id: int = QParam(...),
    limit: int = QParam(20, ge=1, le=100),
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await SlowLogService.get_instance_or_404(db, instance_id, user)
    items = await SlowLogService.fingerprints(db, user, instance_id=instance_id, limit=limit)
    return {"items": [item.model_dump() for item in items]}
