"""
在线查询路由（Sprint 2）。
完整实现：执行查询、权限校验、数据脱敏、查询日志。
"""

import csv
import logging
from io import BytesIO, StringIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Query as QParam
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import current_user
from app.engines.registry import get_engine
from app.models.instance import Instance, InstanceDatabase
from app.schemas.query import QueryExecuteRequest
from app.services.masking import DataMaskingService
from app.services.masking_rule import MaskingRuleService
from app.services.query_guard import get_query_guard
from app.services.query_priv import QueryPrivService

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_instance(db: AsyncSession, instance_id: int) -> Instance:
    result = await db.execute(
        select(Instance)
        .options(selectinload(Instance.resource_groups))
        .where(Instance.id == instance_id, Instance.is_active)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, f"实例 ID={instance_id} 不存在或已停用")
    return inst


async def _run_query_with_permissions(
    db: AsyncSession,
    user: dict,
    data: QueryExecuteRequest,
    operation_type: str = "execute",
    export_format: str = "",
    client_ip: str = "",
) -> tuple[Instance, dict]:
    inst = await _load_instance(db, data.instance_id)
    engine = get_engine(inst)

    guard = get_query_guard(inst.db_type)
    guard_result = guard.validate(data.sql, data.db_name)
    if not guard_result.allowed:
        raise HTTPException(400, guard_result.reason or "在线查询只允许只读语句")

    passed, reason = await QueryPrivService.check_query_priv(
        db=db,
        user=user,
        instance=inst,
        db_name=data.db_name,
        sql=data.sql,
        table_refs=guard_result.table_refs,
    )
    if not passed:
        raise HTTPException(403, reason)

    if not user.get("is_superuser", False):
        inst_db_result = await db.execute(
            select(InstanceDatabase).where(
                InstanceDatabase.instance_id == data.instance_id,
                InstanceDatabase.db_name == data.db_name,
                InstanceDatabase.is_active.is_(True),
            )
        )
        if not inst_db_result.scalar_one_or_none():
            raise HTTPException(403, f"数据库 {data.db_name} 已禁用或未注册，不可查询")

    effective_limit = await QueryPrivService.get_effective_query_limit(
        db=db,
        user=user,
        instance=inst,
        db_name=data.db_name,
        sql=data.sql,
        requested_limit=data.limit_num,
        table_refs=guard_result.table_refs,
    )
    safe_sql = guard.apply_limit(
        guard_result.normalized_sql or data.sql,
        effective_limit,
        guard_result.statement_kind,
    )
    query_kwargs: dict[str, str] = {}
    pg_search_path = await QueryPrivService.resolve_pg_search_path(
        inst,
        data.db_name,
        data.sql,
        table_refs=guard_result.table_refs,
    )
    if pg_search_path:
        query_kwargs["search_path"] = pg_search_path

    resultset = await engine.query(
        db_name=data.db_name,
        sql=safe_sql,
        limit_num=effective_limit if guard_result.use_driver_limit else 0,
        **query_kwargs,
    )
    if resultset.error:
        raise HTTPException(400, f"查询执行失败：{resultset.error}")

    if effective_limit > 0 and len(resultset.rows) > effective_limit:
        resultset.rows = resultset.rows[:effective_limit]
        resultset.affected_rows = len(resultset.rows)

    active_rules = await MaskingRuleService.get_rules_for_instance(
        db, data.instance_id, data.db_name
    )
    masking_svc = DataMaskingService(rules=active_rules)
    masked_result = masking_svc.mask_result(resultset, data.sql, inst.db_type)
    is_masked = masked_result is not resultset
    if operation_type == "export" and data.export_limit:
        start = data.export_offset or 0
        masked_result.rows = masked_result.rows[start:start + data.export_limit]
        masked_result.affected_rows = len(masked_result.rows)

    try:
        await QueryPrivService.write_log(
            db=db,
            user_id=user["id"],
            instance_id=inst.id,
            db_name=data.db_name,
            sql=data.sql,
            effect_row=masked_result.affected_rows,
            cost_time_ms=masked_result.cost_time,
            priv_check=passed,
            hit_rule=False,
            masking=is_masked,
            operation_type=operation_type,
            export_format=export_format,
            username=user.get("username") or user.get("display_name") or "",
            instance_name=inst.instance_name,
            db_type=inst.db_type,
            client_ip=client_ip,
        )
    except Exception as e:
        logger.warning("write_query_log failed: %s", str(e))

    rows_as_list = []
    for row in masked_result.rows:
        if isinstance(row, (tuple, list)):
            rows_as_list.append(
                [
                    str(v) if v is not None and not isinstance(v, (int, float, bool, str)) else v
                    for v in row
                ]
            )
        elif isinstance(row, dict):
            rows_as_list.append(list(row.values()))
        else:
            rows_as_list.append([str(row)])

    return inst, {
        "column_list": masked_result.column_list,
        "rows": rows_as_list,
        "affected_rows": masked_result.affected_rows,
        "cost_time_ms": masked_result.cost_time,
        "is_masked": is_masked,
        "error": "",
    }


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _write_failed_query_log(
    db: AsyncSession,
    user: dict,
    data: QueryExecuteRequest,
    operation_type: str,
    export_format: str,
    client_ip: str,
    error: str,
) -> None:
    try:
        await db.rollback()
        inst = None
        if data.instance_id:
            result = await db.execute(select(Instance).where(Instance.id == data.instance_id))
            inst = result.scalar_one_or_none()
        await QueryPrivService.write_log(
            db=db,
            user_id=user.get("id"),
            instance_id=inst.id if inst else None,
            db_name=data.db_name,
            sql=data.sql,
            effect_row=0,
            cost_time_ms=0,
            priv_check=False,
            hit_rule=False,
            masking=False,
            operation_type=operation_type,
            export_format=export_format,
            username=user.get("username") or user.get("display_name") or "",
            instance_name=inst.instance_name if inst else "",
            db_type=inst.db_type if inst else "",
            client_ip=client_ip,
            error=error,
        )
    except Exception as e:
        logger.warning("write_failed_query_log failed: %s", str(e))


def _build_query_export_file(result: dict, export_format: str) -> tuple[bytes, str, str]:
    headers = ["row_num", *(result.get("column_list") or [])]
    rows = [
        [idx + 1, *row]
        for idx, row in enumerate(result.get("rows") or [])
    ]

    fmt = export_format.lower()
    if fmt == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return (
            output.getvalue().encode("utf-8-sig"),
            "text/csv; charset=utf-8",
            "query_result.csv",
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "QueryResult"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    content = BytesIO()
    wb.save(content)
    return (
        content.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "query_result.xlsx",
    )


@router.post("/", summary="执行在线查询")
async def execute_query(
    data: QueryExecuteRequest,
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    执行在线查询，完整流程：
    1. 加载实例
    2. 查询权限校验（sqlglot 解析表引用，替代 goInception）
    3. 引擎执行查询
    4. 数据脱敏（sqlglot 解析列引用，支持所有方言）
    5. 写入查询日志
    """
    client_ip = _client_ip(request)
    try:
        _, result = await _run_query_with_permissions(
            db=db,
            user=user,
            data=data,
            operation_type="execute",
            client_ip=client_ip,
        )
        return result
    except HTTPException as e:
        await _write_failed_query_log(
            db,
            user,
            data,
            operation_type="execute",
            export_format="",
            client_ip=client_ip,
            error=str(e.detail),
        )
        raise


@router.post("/export/", summary="导出在线查询结果")
async def export_query_result(
    data: QueryExecuteRequest,
    request: Request,
    export_format: str = QParam("xlsx", pattern="^(xlsx|csv)$"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    client_ip = _client_ip(request)
    try:
        _, result = await _run_query_with_permissions(
            db=db,
            user=user,
            data=data,
            operation_type="export",
            export_format=export_format,
            client_ip=client_ip,
        )
        content, media_type, filename = _build_query_export_file(result, export_format)
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        return StreamingResponse(iter([content]), media_type=media_type, headers=headers)
    except HTTPException as e:
        await _write_failed_query_log(
            db,
            user,
            data,
            operation_type="export",
            export_format=export_format,
            client_ip=client_ip,
            error=str(e.detail),
        )
        raise


@router.post("/access-check/", summary="查询权限排查")
async def explain_query_access(
    data: QueryExecuteRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await _load_instance(db, data.instance_id)
    guard = get_query_guard(inst.db_type)
    guard_result = guard.validate(data.sql, data.db_name)
    if not guard_result.allowed:
        return {
            "instance_id": data.instance_id,
            "db_name": data.db_name,
            "allowed": False,
            "reason": guard_result.reason or "在线查询只允许只读语句",
            "layer": "query_guard",
        }
    explanation = await QueryPrivService.explain_query_access(
        db=db,
        user=user,
        instance=inst,
        db_name=data.db_name,
        sql=data.sql,
        table_refs=guard_result.table_refs,
    )
    return {
        "instance_id": data.instance_id,
        "db_name": data.db_name,
        **explanation,
    }


@router.get("/logs/", summary="查询日志列表")
async def list_query_logs(
    instance_id: int | None = None,
    username: str | None = None,
    db_name: str | None = None,
    operation_type: str | None = QParam(None, pattern="^(execute|export)$"),
    masking: bool | None = None,
    sql_keyword: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, logs = await QueryPrivService.list_logs(
        db,
        user=user,
        instance_id=instance_id,
        username=username,
        db_name=db_name,
        operation_type=operation_type,
        masking=masking,
        sql_keyword=sql_keyword,
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
                "user_id": log.user_id,
                "username": log.username,
                "instance_id": log.instance_id,
                "instance_name": log.instance_name,
                "db_type": log.db_type,
                "db_name": log.db_name,
                "sqllog": log.sqllog,
                "operation_type": log.operation_type,
                "export_format": log.export_format,
                "effect_row": log.effect_row,
                "cost_time_ms": log.cost_time_ms,
                "priv_check": log.priv_check,
                "hit_rule": log.hit_rule,
                "masking": log.masking,
                "is_favorite": log.is_favorite,
                "client_ip": log.client_ip,
                "error": log.error,
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
            for log in logs
        ],
    }


@router.post("/logs/{log_id}/favorite/", summary="收藏/取消收藏查询")
async def toggle_favorite(
    log_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.query import QueryLog

    result = await db.execute(
        select(QueryLog).where(QueryLog.id == log_id, QueryLog.user_id == user["id"])
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(404, "查询日志不存在")
    log.is_favorite = not log.is_favorite
    await db.commit()
    return {"status": 0, "is_favorite": log.is_favorite}
