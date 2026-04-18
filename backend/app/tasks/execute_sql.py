"""
SQL 工单异步执行 Celery 任务（Sprint 3）。
"""
import asyncio
import importlib
import json
import logging
from datetime import UTC, datetime

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="execute_workflow", max_retries=0, queue="execute")
def execute_workflow_task(self, workflow_id: int, operator_id: int):
    """
    异步执行 SQL 工单。
    在 Celery worker 进程中创建新的 asyncio event loop 执行。
    """
    logger.info("execute_workflow_task start: workflow_id=%s", workflow_id)
    try:
        asyncio.run(_execute_async(workflow_id, operator_id))
        logger.info("execute_workflow_task done: workflow_id=%s", workflow_id)
    except Exception as e:
        logger.error("execute_workflow_task failed: workflow_id=%s error=%s", workflow_id, str(e))
        raise


async def _execute_async(workflow_id: int, operator_id: int):
    """异步执行逻辑。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import selectinload, sessionmaker

    from app.core.config import settings
    from app.engines.registry import get_engine
    from app.models.instance import Instance
    from app.models.user import Users
    from app.models.workflow import SqlWorkflow, WorkflowAudit, WorkflowStatus
    from app.services.audit import OP_EXECUTE, AuditService

    importlib.import_module("app.models")  # 预加载全部模型，确保 metadata 中包含审批流等外键目标表

    engine = create_async_engine(settings.DATABASE_URL)
    async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_local() as db:
        # 加载工单
        result = await db.execute(
            select(SqlWorkflow)
            .options(selectinload(SqlWorkflow.content))
            .where(SqlWorkflow.id == workflow_id)
        )
        wf = result.scalar_one_or_none()
        if not wf:
            logger.error("workflow not found: %s", workflow_id)
            return

        # 加载操作人
        user_result = await db.execute(select(Users).where(Users.id == operator_id))
        user = user_result.scalar_one_or_none()
        operator = {"id": operator_id, "username": user.username if user else "system"}

        # 加载实例
        inst_result = await db.execute(
            select(Instance).where(Instance.id == wf.instance_id)
        )
        inst = inst_result.scalar_one_or_none()
        if not inst:
            wf.status = WorkflowStatus.EXCEPTION
            await db.commit()
            return

        # 更新为执行中
        wf.status = WorkflowStatus.EXECUTING
        await db.commit()

        # 执行 SQL
        db_engine = get_engine(inst)
        sql = wf.content.sql_content if wf.content else ""

        try:
            review_set = await db_engine.execute(db_name=wf.db_name, sql=sql)
            result_json = json.dumps(
                {"success": not review_set.error, "error": review_set.error or ""},
                ensure_ascii=False,
            )
            if wf.content:
                wf.content.execute_result = result_json
            wf.status = WorkflowStatus.FINISH if not review_set.error else WorkflowStatus.EXCEPTION
        except Exception as e:
            if wf.content:
                wf.content.execute_result = json.dumps({"error": str(e)})
            wf.status = WorkflowStatus.EXCEPTION

        wf.finish_time = datetime.now(UTC)

        # 写日志
        audit_result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == wf.id)
        )
        audit = audit_result.scalar_one_or_none()
        if audit:
            await AuditService._write_log(
                db, audit.id, operator, OP_EXECUTE,
                remark=f"执行完成，状态：{wf.status}"
            )
        await db.commit()

    await engine.dispose()
