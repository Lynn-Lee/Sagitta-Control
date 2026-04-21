"""
SQL 工单路由（Sprint 3）。
"""
import contextlib
import logging

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi import Query as QParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.schemas.workflow import (
    WorkflowAuditRequest,
    WorkflowCheckRequest,
    WorkflowCreateRequest,
    WorkflowExecuteRequest,
)
from app.services.audit import AuditService
from app.services.audit_log import AuditLogService
from app.services.notify import NotifyService
from app.services.workflow import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="工单列表")
async def list_workflows(
    view: str = QParam("mine", description="mine|audit|execute|scope"),
    status: int | None = None,
    instance_id: int | None = None,
    search: str | None = None,
    engineer: str | None = QParam(None, description="提交人用户名/显示名模糊查询"),
    db_name: str | None = QParam(None, description="数据库名模糊查询"),
    date_start: str | None = QParam(None, description="提交时间开始 yyyy-mm-dd"),
    date_end: str | None = QParam(None, description="提交时间结束 yyyy-mm-dd"),
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items, scope = await WorkflowService.list_workflows(
        db, user=user, view=view, status=status, instance_id=instance_id,
        search=search, engineer=engineer, db_name=db_name,
        date_start=date_start, date_end=date_end,
        page=page, page_size=page_size,
    )
    payload = {"total": total, "page": page, "page_size": page_size, "items": items}
    if scope:
        payload["scope"] = scope
    return payload


@router.post("/", summary="提交工单", dependencies=[Depends(require_perm("sql_submit"))])
async def create_workflow(
    data: WorkflowCreateRequest,
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await WorkflowService.create(db, data, operator=user)
    await AuditLogService.write(
        db, user, action="submit_workflow", module="workflow",
        detail=f"提交工单 #{wf.id}：{wf.workflow_name}，实例ID={data.instance_id}，库={data.db_name}",
        request=request,
    )
    # 通知审批人
    import asyncio
    asyncio.create_task(NotifyService.notify_workflow(
        db=db, workflow_id=wf.id, workflow_name=wf.workflow_name,
        status=0, operator=user.get("username", ""),
        db_name=data.db_name,
        remark="工单已提交，待审批",
    ))
    return {"status": 0, "msg": "工单提交成功", "data": {"id": wf.id, "workflow_name": wf.workflow_name}}


@router.get("/pending/", summary="待我审核的工单")
async def pending_workflows(
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await WorkflowService.pending_for_me(db, user, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/check/", summary="SQL 预检查（不提交工单）")
async def check_sql(
    data: WorkflowCheckRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    results = await WorkflowService.check_sql(db, data.instance_id, data.db_name, data.sql_content)
    return {"status": 0, "data": results}


@router.get("/{workflow_id}/", summary="工单详情")
async def get_workflow(
    workflow_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await WorkflowService.get_detail(db, workflow_id, user)


@router.post("/{workflow_id}/audit/", summary="审核工单")
async def audit_workflow(
    workflow_id: int,
    data: WorkflowAuditRequest,
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await AuditService.operate(
        db, workflow_id=workflow_id, action=data.action,
        operator=user, remark=data.remark,
    )
    action_desc = "审批通过" if data.action == "pass" else "审批驳回"
    await AuditLogService.write(
        db, user, action=f"audit_workflow_{data.action}", module="workflow",
        detail=f"{action_desc}工单 #{workflow_id}，备注：{data.remark or '无'}",
        request=request,
    )
    # 通知工单提交人
    new_status = result.get("status", 2 if data.action == "pass" else 1)
    import asyncio
    asyncio.create_task(NotifyService.notify_workflow(
        db=db, workflow_id=workflow_id, workflow_name=f"工单#{workflow_id}",
        status=new_status, operator=user.get("username", ""),
        remark=data.remark or action_desc,
    ))
    return {"status": 0, **result}


@router.post("/{workflow_id}/execute/", summary="执行工单", dependencies=[Depends(require_perm("sql_execute"))])
async def execute_workflow(
    workflow_id: int,
    data: WorkflowExecuteRequest = WorkflowExecuteRequest(),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await WorkflowService.execute(db, workflow_id, operator=user, mode=data.mode)
    return {"status": 0, **result}


@router.post("/{workflow_id}/cancel/", summary="取消工单")
async def cancel_workflow(
    workflow_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await AuditService.operate(
        db, workflow_id=workflow_id, action="cancel", operator=user
    )
    return {"status": 0, **result}


@router.get("/{workflow_id}/status/", summary="查询工单当前状态")
async def get_workflow_status(
    workflow_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.workflow import SqlWorkflow
    from app.services.workflow import STATUS_DESC
    result = await db.execute(select(SqlWorkflow).where(SqlWorkflow.id == workflow_id))
    wf = result.scalar_one_or_none()
    if not wf:
        from fastapi import HTTPException
        raise HTTPException(404, "工单不存在")
    return {
        "workflow_id": workflow_id,
        "status": wf.status,
        "status_desc": STATUS_DESC.get(wf.status, "未知"),
        "finish_time": wf.finish_time.isoformat() if wf.finish_time else None,
    }


# ── WebSocket 进度推送 ────────────────────────────────────────

@router.websocket("/{workflow_id}/progress/")
async def workflow_progress_ws(
    workflow_id: int,
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket：实时推送工单执行进度。
    每秒查询一次状态，直到终态（finish/exception/abort）或客户端断开。
    """
    await websocket.accept()
    import asyncio

    from sqlalchemy import select

    from app.models.workflow import SqlWorkflow
    from app.services.workflow import STATUS_DESC

    terminal_states = {6, 7, 8}  # FINISH, EXCEPTION, ABORT
    try:
        while True:
            result = await db.execute(
                select(SqlWorkflow).where(SqlWorkflow.id == workflow_id)
            )
            wf = result.scalar_one_or_none()
            if not wf:
                await websocket.send_json({"error": "工单不存在"})
                break
            await websocket.send_json({
                "workflow_id": workflow_id,
                "status": wf.status,
                "status_desc": STATUS_DESC.get(wf.status, "未知"),
                "finish_time": wf.finish_time.isoformat() if wf.finish_time else None,
            })
            if wf.status in terminal_states:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("ws_disconnected: workflow_id=%s", workflow_id)
    except Exception as e:
        logger.error("ws_error: %s", str(e))
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
