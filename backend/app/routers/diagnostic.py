"""
会话/锁/事务诊断路由（Sprint 4）。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi import Query as QParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.schemas.diagnostic import (
    KillSessionRequest,
    SessionCollectConfigItem,
    SessionCollectConfigListResponse,
    SessionCollectConfigUpdate,
    SessionCollectConfigUpsert,
    SessionHistoryResponse,
    SessionListResponse,
)
from app.services.audit_log import AuditLogService
from app.services.session_diagnostic import SessionDiagnosticService, items_to_legacy_rows

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_instance(db: AsyncSession, instance_id: int) -> Instance:
    result = await db.execute(select(Instance).where(Instance.id == instance_id, Instance.is_active))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, f"实例 ID={instance_id} 不存在")
    return inst


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, f"时间格式错误：{value}") from exc


@router.get(
    "/processlist/",
    summary="查看会话列表",
    response_model=SessionListResponse,
    dependencies=[Depends(require_perm("process_view"))],
)
async def get_processlist(
    instance_id: int = QParam(..., description="实例ID"),
    command_type: str = "ALL",
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await _get_instance(db, instance_id)
    engine = get_engine(inst)
    rs = await engine.processlist(command_type=command_type)
    if rs.error:
        raise HTTPException(400, f"获取会话列表失败：{rs.error}")
    items = SessionDiagnosticService.normalize_result(inst, rs)
    columns, rows = items_to_legacy_rows(items)
    return {
        "items": items,
        "column_list": columns,
        "rows": rows,
        "total": len(items),
    }


@router.get(
    "/sessions/history/",
    summary="查看历史会话采样",
    response_model=SessionHistoryResponse,
    dependencies=[Depends(require_perm("process_view"))],
)
async def list_session_history(
    instance_id: int | None = None,
    db_type: str | None = None,
    username: str | None = None,
    db_name: str | None = None,
    sql_keyword: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    min_seconds: int | None = QParam(default=None, ge=0),
    min_duration_ms: int | None = QParam(default=None, ge=0),
    page: int = QParam(default=1, ge=1),
    page_size: int = QParam(default=50, ge=1, le=200),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await SessionDiagnosticService.list_history(
        db,
        instance_id=instance_id,
        db_type=db_type,
        username=username,
        db_name=db_name,
        sql_keyword=sql_keyword,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        min_seconds=min_seconds,
        min_duration_ms=min_duration_ms,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "items": items}


@router.get(
    "/sessions/configs/",
    summary="查看会话采集配置",
    response_model=SessionCollectConfigListResponse,
    dependencies=[Depends(require_perm("process_view"))],
)
async def list_session_collect_configs(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await SessionDiagnosticService.list_configs(db, user)
    return {"total": total, "items": items}


@router.post(
    "/sessions/configs/",
    summary="创建或更新会话采集配置",
    response_model=SessionCollectConfigItem,
    dependencies=[Depends(require_perm("process_kill"))],
)
async def upsert_session_collect_config(
    data: SessionCollectConfigUpsert,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await SessionDiagnosticService.upsert_config(db, data, user)
    inst = await _get_instance(db, cfg.instance_id)
    return SessionCollectConfigItem(
        id=cfg.id,
        instance_id=cfg.instance_id,
        instance_name=inst.instance_name,
        db_type=inst.db_type,
        is_enabled=cfg.is_enabled,
        collect_interval=cfg.collect_interval,
        retention_days=cfg.retention_days,
        last_collect_at=cfg.last_collect_at,
        last_collect_status=cfg.last_collect_status,
        last_collect_error=cfg.last_collect_error,
        last_collect_count=cfg.last_collect_count,
        created_by=cfg.created_by,
    )


@router.put(
    "/sessions/configs/{config_id}/",
    summary="更新会话采集配置",
    response_model=SessionCollectConfigItem,
    dependencies=[Depends(require_perm("process_kill"))],
)
async def update_session_collect_config(
    config_id: int,
    data: SessionCollectConfigUpdate,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    cfg = await SessionDiagnosticService.update_config(db, config_id, data, user)
    inst = await _get_instance(db, cfg.instance_id)
    return SessionCollectConfigItem(
        id=cfg.id,
        instance_id=cfg.instance_id,
        instance_name=inst.instance_name,
        db_type=inst.db_type,
        is_enabled=cfg.is_enabled,
        collect_interval=cfg.collect_interval,
        retention_days=cfg.retention_days,
        last_collect_at=cfg.last_collect_at,
        last_collect_status=cfg.last_collect_status,
        last_collect_error=cfg.last_collect_error,
        last_collect_count=cfg.last_collect_count,
        created_by=cfg.created_by,
    )


@router.get(
    "/sessions/oracle-ash/",
    summary="Oracle ASH/AWR 历史会话",
    response_model=SessionHistoryResponse,
    dependencies=[Depends(require_perm("process_view"))],
)
async def list_oracle_ash_history(
    instance_id: int = QParam(...),
    source: str = QParam(default="ash", pattern="^(ash|awr)$"),
    date_start: str | None = None,
    date_end: str | None = None,
    sql_keyword: str | None = None,
    min_duration_ms: int | None = QParam(default=None, ge=0),
    page: int = QParam(default=1, ge=1),
    page_size: int = QParam(default=50, ge=1, le=200),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await _get_instance(db, instance_id)
    if inst.db_type != "oracle":
        raise HTTPException(400, "ASH/AWR 历史仅支持 Oracle 实例")
    engine = get_engine(inst)
    if not hasattr(engine, "ash_history"):
        raise HTTPException(400, "当前 Oracle 引擎暂不支持 ASH/AWR 历史")
    rs = await engine.ash_history(
        source=source,
        date_start=_parse_dt(date_start),
        date_end=_parse_dt(date_end),
        sql_keyword=sql_keyword,
        min_duration_ms=min_duration_ms,
        limit_num=page_size,
        offset=(page - 1) * page_size,
    )
    if rs.error:
        raise HTTPException(400, f"获取 Oracle ASH/AWR 历史失败：{rs.error}")
    items = SessionDiagnosticService.normalize_result(inst, rs, source=f"oracle_{source}")
    return {"total": rs.affected_rows or len(items), "items": items}


@router.post("/kill/", summary="Kill 会话", dependencies=[Depends(require_perm("process_kill"))])
async def kill_session(
    request: Request,
    payload: KillSessionRequest | None = Body(default=None),
    instance_id: int | None = None,
    thread_id: int | None = None,
    session_id: str | None = None,
    serial: str = "",
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload is not None:
        instance_id = payload.instance_id
        session_id = payload.session_id
        serial = payload.serial
    elif thread_id is not None:
        session_id = str(thread_id)

    if not instance_id or not session_id:
        raise HTTPException(400, "缺少 instance_id 或 session_id")

    inst = await _get_instance(db, instance_id)
    engine = get_engine(inst)

    if hasattr(engine, 'kill_connection'):
        if inst.db_type == "oracle":
            if not serial:
                raise HTTPException(400, "Oracle Kill 会话必须提供 serial")
            rs = await engine.kill_connection(int(session_id), serial=serial)
        else:
            rs = await engine.kill_connection(int(session_id))
        if rs.error:
            await AuditLogService.write(
                db=db,
                user=user,
                action="kill_session",
                module="session",
                detail=f"instance={inst.instance_name}, session_id={session_id}, serial={serial}",
                result="failed",
                request=request,
                remark=rs.error,
            )
            raise HTTPException(400, f"Kill 失败：{rs.error}")
        await AuditLogService.write(
            db=db,
            user=user,
            action="kill_session",
            module="session",
            detail=f"instance={inst.instance_name}, session_id={session_id}, serial={serial}",
            result="success",
            request=request,
        )
        return {"status": 0, "msg": f"已 Kill 会话 {session_id}"}
    else:
        raise HTTPException(400, f"{inst.db_type} 引擎暂不支持 Kill 操作")


@router.get("/variables/", summary="实例参数列表")
async def get_variables(
    instance_id: int = QParam(...),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    inst = await _get_instance(db, instance_id)
    engine = get_engine(inst)
    rs = await engine.get_variables()
    if rs.error:
        raise HTTPException(400, f"获取参数失败：{rs.error}")
    cols = rs.column_list or []
    return {
        "params": [dict(zip(cols, r, strict=False)) if isinstance(r, tuple) else r for r in rs.rows]
    }
