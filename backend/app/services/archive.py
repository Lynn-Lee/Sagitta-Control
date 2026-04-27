"""Data archive service with approval-backed background jobs."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import sqlglot
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.engines.registry import get_engine
from app.models.archive import ArchiveBatchLog, ArchiveBatchStatus, ArchiveJob, ArchiveJobStatus
from app.models.instance import Instance
from app.models.user import Users
from app.models.workflow import (
    SqlWorkflow,
    SqlWorkflowContent,
    WorkflowAudit,
    WorkflowStatus,
    WorkflowType,
)
from app.services.audit import OP_EXECUTE, OP_TIMING, AuditService
from app.services.cancel_policy import ApplicationCancelPolicy
from app.services.risk_plan import RiskPlanService
from app.services.workflow import WorkflowService

logger = logging.getLogger(__name__)

ARCHIVE_SUPPORT: dict[str, dict[str, Any]] = {
    "mysql": {"purge": True, "dest": True, "batch_delete": "limit", "verified": True},
    "tidb": {"purge": True, "dest": True, "batch_delete": "limit", "verified": False},
    "doris": {"purge": False, "dest": False, "batch_delete": "limit", "reason": "Doris 引擎仍待真实环境验证"},
    "pgsql": {"purge": True, "dest": True, "batch_delete": "ctid", "verified": True},
    "oracle": {"purge": True, "dest": True, "batch_delete": "rownum", "verified": False},
    "mssql": {"purge": True, "dest": True, "batch_delete": "top", "verified": False},
    "starrocks": {"purge": True, "dest": False, "batch_delete": "where", "verified": False},
    "clickhouse": {"purge": True, "dest": False, "batch_delete": "ch_alter", "verified": False},
    "mongo": {"purge": True, "dest": True, "batch_delete": "mongo", "verified": True},
    "cassandra": {"purge": False, "dest": False, "reason": "Cassandra 归档需主键发现，首轮默认关闭"},
    "redis": {"purge": False, "dest": False, "reason": "Redis 为键值存储，不支持条件归档"},
    "elasticsearch": {"purge": False, "dest": False, "reason": "Elasticsearch 请使用 ILM 生命周期管理"},
    "opensearch": {"purge": False, "dest": False, "reason": "OpenSearch 请使用 ISM 策略管理"},
}

SQLGLOT_DIALECTS = {
    "mysql": "mysql",
    "tidb": "mysql",
    "doris": "mysql",
    "starrocks": "mysql",
    "pgsql": "postgres",
    "postgres": "postgres",
    "postgresql": "postgres",
    "oracle": "oracle",
    "mssql": "tsql",
    "clickhouse": "clickhouse",
}

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
ALWAYS_TRUE_RE = re.compile(
    r"^\s*(?:1\s*=\s*1|true|TRUE)(?:\s+AND\s+(?:1\s*=\s*1|true|TRUE))*\s*$"
)
SQL_STATEMENT_PREFIX_RE = re.compile(r"^\s*(?:select|delete|update|insert|replace|truncate|alter|drop)\b", re.IGNORECASE)


def check_support(db_type: str, mode: str) -> tuple[bool, str]:
    cfg = ARCHIVE_SUPPORT.get(db_type.lower())
    if not cfg:
        return False, f"数据库类型 {db_type} 未在支持列表中，暂不支持数据归档"
    if not cfg.get(mode):
        return False, cfg.get("reason", f"{db_type} 不支持 {mode} 归档模式")
    return True, ""


def _quote_identifier(db_type: str, name: str) -> str:
    if not IDENT_RE.match(name):
        raise AppException(f"非法标识符：{name}", code=400)
    dt = db_type.lower()
    if dt in ("pgsql", "oracle"):
        return f'"{name}"'
    if dt == "mssql":
        return f"[{name}]"
    if dt == "clickhouse":
        return f"`{name}`"
    return f"`{name}`"


def build_batch_delete_sql(db_type: str, table_name: str, condition: str, batch_size: int) -> str:
    dt = db_type.lower()
    t = _quote_identifier(dt, table_name)
    if dt in ("mysql", "tidb"):
        return f"DELETE FROM {t} WHERE {condition} LIMIT {batch_size}"
    if dt == "pgsql":
        return f"DELETE FROM {t} WHERE ctid IN (SELECT ctid FROM {t} WHERE {condition} LIMIT {batch_size})"
    if dt == "oracle":
        return f"DELETE FROM {t} WHERE ROWID IN (SELECT ROWID FROM {t} WHERE {condition} AND ROWNUM <= {batch_size})"
    if dt == "mssql":
        return f"DELETE TOP({batch_size}) FROM {t} WHERE {condition}"
    if dt == "starrocks":
        return f"DELETE FROM {t} WHERE {condition}"
    if dt == "clickhouse":
        return f"ALTER TABLE {t} DELETE WHERE {condition}"
    return f"DELETE FROM {t} WHERE {condition} LIMIT {batch_size}"


def build_count_sql(db_type: str, table_name: str, condition: str) -> str:
    dt = db_type.lower()
    t = _quote_identifier(dt, table_name)
    if dt == "clickhouse":
        return f"SELECT count() FROM {t} WHERE {condition}"
    return f"SELECT COUNT(*) FROM {t} WHERE {condition}"


def validate_archive_condition(db_type: str, table_name: str, condition: str) -> None:
    """Reject unsafe archive predicates before they reach engine execution."""
    if db_type == "mongo":
        try:
            parsed = json.loads(condition)
        except Exception as exc:
            raise AppException("MongoDB 归档条件必须是合法 JSON", code=400) from exc
        if not isinstance(parsed, dict) or not parsed:
            raise AppException("MongoDB 归档条件不能为空对象", code=400)
        return

    cond = condition.strip()
    if not cond:
        raise AppException("归档条件不能为空", code=400)
    if SQL_STATEMENT_PREFIX_RE.match(cond):
        raise AppException(
            "归档条件只填写 WHERE 后面的条件，无需填写完整 SQL。示例：created_at < '2024-01-01'",
            code=400,
        )
    if ";" in cond or "--" in cond or "/*" in cond or "*/" in cond:
        raise AppException("归档条件不能包含多语句或注释", code=400)
    if ALWAYS_TRUE_RE.match(cond):
        raise AppException("归档条件不能是明显全表条件", code=400)
    if not IDENT_RE.match(table_name):
        raise AppException(f"非法表名：{table_name}", code=400)

    dialect = SQLGLOT_DIALECTS.get(db_type.lower(), "mysql")
    try:
        sqlglot.parse_one(f"SELECT 1 FROM {_quote_identifier(db_type, table_name)} WHERE {cond}", dialect=dialect)
    except Exception as exc:
        raise AppException(f"归档条件 SQL 解析失败：{str(exc)}", code=400) from exc


class ArchiveService:
    @staticmethod
    def _first_value(row: Any) -> Any:
        if isinstance(row, dict):
            return next(iter(row.values()), 0)
        if isinstance(row, (tuple, list)):
            return row[0] if row else 0
        return row

    @staticmethod
    def _review_affected_rows(review_set: Any, fallback: int = 0) -> tuple[int, bool]:
        rows = getattr(review_set, "rows", []) or []
        affected = sum(max(int(getattr(item, "affected_rows", 0) or 0), 0) for item in rows)
        if affected > 0:
            return affected, False
        return fallback, True

    @staticmethod
    async def _load_instance(db: AsyncSession, instance_id: int) -> Instance:
        result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == instance_id)
        )
        inst = result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        return inst

    @staticmethod
    def _assert_instance_scope(inst: Instance, user: dict) -> tuple[int, str]:
        if user.get("is_superuser"):
            rgs = [rg for rg in inst.resource_groups if rg.is_active]
            return (rgs[0].id, rgs[0].group_name) if rgs else (0, "默认资源组")
        user_rg_ids = set(user.get("resource_groups", []))
        matched = [rg for rg in inst.resource_groups if rg.is_active and rg.id in user_rg_ids]
        if not matched:
            raise AppException("目标实例不在你的资源组访问范围内", code=403)
        rg = sorted(matched, key=lambda item: item.id)[0]
        return rg.id, rg.group_name

    @staticmethod
    def _has_archive_execute(user: dict) -> bool:
        return bool(user.get("is_superuser") or "archive_execute" in user.get("permissions", []))

    @staticmethod
    def _assert_archive_execute_scope(job: ArchiveJob, src_inst: Instance, user: dict) -> None:
        if user.get("is_superuser"):
            return
        if "archive_execute" not in user.get("permissions", []):
            raise AppException("没有归档执行权限", code=403)
        if user.get("role") == "dba" or "query_all_instances" in user.get("permissions", []):
            return
        user_rg_ids = set(user.get("resource_groups", []))
        matched = {rg.id for rg in src_inst.resource_groups if rg.is_active and rg.id in user_rg_ids}
        if not matched:
            raise AppException("目标实例不在你的资源组执行范围内", code=403)

    @staticmethod
    async def estimate_rows(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        table_name: str,
        condition: str,
        archive_mode: str = "purge",
        batch_size: int = 1000,
        dest_db: str | None = None,
        dest_table: str | None = None,
    ) -> dict:
        inst = await ArchiveService._load_instance(db, instance_id)
        supported, reason = check_support(inst.db_type, "purge")
        if not supported:
            return {"count": -1, "supported": False, "msg": reason}
        validate_archive_condition(inst.db_type, table_name, condition)
        engine = get_engine(inst)

        if inst.db_type == "mongo":
            client = await engine.get_connection(db_name)
            count = await client[db_name][table_name].count_documents(json.loads(condition))
            plan = RiskPlanService.build_archive_plan(inst.db_type, archive_mode, db_name, table_name, condition, batch_size, count, dest_db, dest_table)
            return {"count": count, "supported": True, "msg": f"符合条件：{count} 条文档", "db_type": inst.db_type, "risk_plan": plan.model_dump()}

        count_sql = build_count_sql(inst.db_type, table_name, condition)
        rs = await engine.query(db_name=db_name, sql=count_sql, limit_num=1)
        if rs.error:
            return {"count": -1, "supported": True, "msg": f"估算失败：{rs.error}"}
        count = int(ArchiveService._first_value(rs.rows[0]) if rs.rows else 0)
        plan = RiskPlanService.build_archive_plan(inst.db_type, archive_mode, db_name, table_name, condition, batch_size, count, dest_db, dest_table)
        return {"count": count, "supported": True, "msg": f"符合条件的数据：{count} 行", "db_type": inst.db_type, "risk_plan": plan.model_dump()}

    @staticmethod
    async def submit_job(db: AsyncSession, data: Any, operator: dict) -> ArchiveJob:
        src_inst = await ArchiveService._load_instance(db, data.source_instance_id)
        rg_id, rg_name = ArchiveService._assert_instance_scope(src_inst, operator)
        supported, reason = check_support(src_inst.db_type, data.archive_mode)
        if not supported:
            raise AppException(reason, code=400)
        validate_archive_condition(src_inst.db_type, data.source_table, data.condition)

        if data.archive_mode == "dest":
            if not data.dest_instance_id:
                raise AppException("归档模式为 dest 时必须填写目标实例", code=400)
            dest_inst = await ArchiveService._load_instance(db, data.dest_instance_id)
            ArchiveService._assert_instance_scope(dest_inst, operator)

        estimate = await ArchiveService.estimate_rows(
            db, data.source_instance_id, data.source_db, data.source_table, data.condition,
            data.archive_mode, data.batch_size, data.dest_db, data.dest_table
        )
        if estimate.get("count", -1) < 0:
            raise AppException(estimate.get("msg", "归档估算失败"), code=400)
        risk_plan = RiskPlanService.build_archive_plan(
            db_type=src_inst.db_type,
            archive_mode=data.archive_mode,
            source_db=data.source_db,
            source_table=data.source_table,
            condition=data.condition,
            batch_size=data.batch_size,
            estimated_rows=int(estimate["count"]),
            dest_db=data.dest_db or data.source_db,
            dest_table=data.dest_table or data.source_table,
        )
        if risk_plan.requires_manual_remark and not (data.risk_remark or "").strip():
            raise AppException("高风险归档/清理申请必须填写恢复/验证说明", code=400)

        workflow = await ArchiveService._create_archive_workflow(
            db, data, operator, rg_id, rg_name, int(estimate["count"]), risk_plan.model_dump()
        )
        job = ArchiveJob(
            workflow_id=workflow.id,
            status=ArchiveJobStatus.PENDING_REVIEW,
            archive_mode=data.archive_mode,
            source_instance_id=data.source_instance_id,
            source_db=data.source_db,
            source_table=data.source_table,
            condition=data.condition,
            dest_instance_id=data.dest_instance_id,
            dest_db=data.dest_db or data.source_db,
            dest_table=data.dest_table or data.source_table,
            batch_size=data.batch_size,
            sleep_ms=data.sleep_ms,
            estimated_rows=int(estimate["count"]),
            apply_reason=data.apply_reason or "",
            risk_plan=json.dumps(risk_plan.model_dump(), ensure_ascii=False),
            risk_level=risk_plan.level,
            risk_summary=risk_plan.summary,
            risk_remark=data.risk_remark or "",
            created_by=operator.get("username", ""),
            created_by_id=operator.get("id", 0),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def _create_archive_workflow(
        db: AsyncSession,
        data: Any,
        operator: dict,
        rg_id: int,
        rg_name: str,
        estimated_rows: int,
        risk_plan: dict | None = None,
    ) -> SqlWorkflow:
        nodes_snapshot = None
        if data.flow_id:
            from app.services.approval_flow import ApprovalFlowService

            nodes_snapshot = await ApprovalFlowService.snapshot_for_workflow(db, data.flow_id)
            nodes_snapshot = WorkflowService._decorate_snapshot_for_applicant(nodes_snapshot, operator)
            for node in nodes_snapshot:
                if node.get("approver_type") == "any_reviewer":
                    node["required_permission"] = "archive_review"
        else:
            nodes_snapshot = [
                {
                    "order": 1,
                    "node_id": None,
                    "node_name": "归档审批",
                    "approver_type": "any_reviewer",
                    "approver_ids": [],
                    "required_permission": "archive_review",
                    "status": 0,
                    "operator": None,
                    "operated_at": None,
                }
            ]

        title = f"数据归档-{data.source_table}"
        sql_content = json.dumps(
            {
                "archive_mode": data.archive_mode,
                "source": {
                    "instance_id": data.source_instance_id,
                    "db": data.source_db,
                    "table": data.source_table,
                    "condition": data.condition,
                },
                "dest": {
                    "instance_id": data.dest_instance_id,
                    "db": data.dest_db or data.source_db,
                    "table": data.dest_table or data.source_table,
                } if data.archive_mode == "dest" else None,
                "batch_size": data.batch_size,
                "sleep_ms": data.sleep_ms,
                "estimated_rows": estimated_rows,
                "apply_reason": data.apply_reason,
            },
            ensure_ascii=False,
            indent=2,
        )
        workflow = SqlWorkflow(
            workflow_name=title[:50],
            group_id=rg_id,
            group_name=rg_name,
            instance_id=data.source_instance_id,
            db_name=data.source_db,
            syntax_type=2,
            is_backup=True,
            engineer=operator.get("username", ""),
            engineer_display=operator.get("display_name", ""),
            engineer_id=operator.get("id", 0),
            status=WorkflowStatus.PENDING_REVIEW,
            audit_auth_groups=str(rg_id),
            flow_id=data.flow_id,
        )
        db.add(workflow)
        await db.flush()
        db.add(SqlWorkflowContent(
            workflow_id=workflow.id,
            sql_content=sql_content,
            review_content="",
            execute_result="",
            risk_plan=json.dumps(risk_plan or {}, ensure_ascii=False),
            risk_remark=data.risk_remark or "",
        ))
        await db.flush()
        await AuditService(workflow, WorkflowType.ARCHIVE).create_audit(db, operator, nodes_snapshot=nodes_snapshot)
        return workflow

    @staticmethod
    async def start_job(db: AsyncSession, job_id: int, operator: dict, data: Any | None = None) -> dict:
        job = await ArchiveService.get_job_obj(db, job_id)
        src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
        ArchiveService._assert_archive_execute_scope(job, src_inst, operator)
        if job.status not in (ArchiveJobStatus.APPROVED, ArchiveJobStatus.PAUSED, ArchiveJobStatus.QUEUED, ArchiveJobStatus.SCHEDULED):
            raise AppException(f"当前状态 {job.status} 不能执行", code=400)
        mode = getattr(data, "mode", "immediate") if data is not None else "immediate"
        if mode == "scheduled":
            return await ArchiveService._schedule_job(db, job, operator, data)
        if mode == "external":
            return await ArchiveService._record_external_job(db, job, operator, data)
        return await ArchiveService._start_job_immediately(db, job, operator)

    @staticmethod
    def _operator_display(operator: dict) -> str:
        return operator.get("display_name") or operator.get("username") or str(operator.get("id", ""))

    @staticmethod
    def _ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    async def _write_execution_log(db: AsyncSession, job: ArchiveJob, operator: dict, operation_type: str, remark: str) -> None:
        if not job.workflow_id:
            return
        audit_result = await db.execute(select(WorkflowAudit).where(WorkflowAudit.workflow_id == job.workflow_id))
        audit = audit_result.scalar_one_or_none()
        if audit:
            await AuditService._write_log(db, audit.id, operator, operation_type, remark=remark)

    @staticmethod
    async def _sync_workflow_execution_decision(
        db: AsyncSession,
        job: ArchiveJob,
        operator: dict,
        *,
        mode: str,
        status: WorkflowStatus,
        scheduled_at: datetime | None = None,
        external_executed_at: datetime | None = None,
        external_status: str | None = None,
        external_remark: str | None = None,
    ) -> None:
        if not job.workflow_id:
            return
        wf = await db.get(SqlWorkflow, job.workflow_id)
        if not wf:
            return
        wf.execute_mode = mode
        wf.executed_by_id = operator.get("id")
        wf.executed_by_name = ArchiveService._operator_display(operator)
        wf.scheduled_execute_at = scheduled_at
        wf.external_executed_at = external_executed_at
        wf.external_result_status = external_status
        wf.external_result_remark = external_remark
        wf.status = status
        if external_executed_at:
            wf.finish_time = external_executed_at
        if mode == "external" and wf.content:
            wf.content.execute_result = json.dumps(
                {
                    "mode": "external",
                    "success": external_status == "success",
                    "status": external_status,
                    "executed_at": external_executed_at.isoformat() if external_executed_at else None,
                    "operator": wf.executed_by_name,
                    "remark": external_remark,
                },
                ensure_ascii=False,
            )

    @staticmethod
    async def _start_job_immediately(db: AsyncSession, job: ArchiveJob, operator: dict) -> dict:
        job.status = ArchiveJobStatus.QUEUED
        job.finished_at = None
        await ArchiveService._sync_workflow_execution_decision(
            db, job, operator, mode="immediate", status=WorkflowStatus.QUEUING
        )
        await ArchiveService._write_execution_log(
            db, job, operator, OP_EXECUTE, "DBA 确认立即平台执行归档作业，已加入执行队列"
        )
        await db.commit()
        try:
            from app.tasks.archive import execute_archive_job_task

            task = execute_archive_job_task.delay(job.id, operator.get("id", 0))
            job.celery_task_id = task.id
            await db.commit()
        except Exception as exc:
            logger.warning("archive celery unavailable: %s", str(exc))
            await ArchiveService.execute_job(db, job.id, operator.get("id", 0))
        await db.refresh(job)
        return {"msg": "归档作业已加入后台队列", "job_id": job.id, "status": job.status}

    @staticmethod
    async def _schedule_job(db: AsyncSession, job: ArchiveJob, operator: dict, data: Any) -> dict:
        scheduled_at = getattr(data, "scheduled_at", None) or getattr(data, "timing_time", None)
        if scheduled_at is None:
            raise AppException("请选择预约执行时间", code=400)
        scheduled_at = ArchiveService._ensure_aware_utc(scheduled_at)
        if scheduled_at <= datetime.now(UTC):
            raise AppException("预约执行时间必须晚于当前时间", code=400)
        job.status = ArchiveJobStatus.SCHEDULED
        job.finished_at = None
        await ArchiveService._sync_workflow_execution_decision(
            db, job, operator, mode="scheduled", status=WorkflowStatus.TIMING_TASK, scheduled_at=scheduled_at
        )
        await ArchiveService._write_execution_log(
            db, job, operator, OP_TIMING, f"DBA 预约平台执行归档作业，预约时间：{scheduled_at.isoformat()}"
        )
        await db.commit()
        await db.refresh(job)
        return {
            "msg": "已预约定时执行",
            "job_id": job.id,
            "workflow_id": job.workflow_id,
            "status": job.status,
            "scheduled_execute_at": scheduled_at.isoformat(),
        }

    @staticmethod
    async def _record_external_job(db: AsyncSession, job: ArchiveJob, operator: dict, data: Any) -> dict:
        executed_at = getattr(data, "external_executed_at", None)
        external_status = getattr(data, "external_status", None)
        remark = (getattr(data, "external_remark", "") or "").strip()
        if executed_at is None:
            raise AppException("请填写外部实际执行时间", code=400)
        if not external_status:
            raise AppException("请选择外部执行结果", code=400)
        if not remark:
            raise AppException("请填写外部执行结果备注", code=400)
        executed_at = ArchiveService._ensure_aware_utc(executed_at)
        job.status = ArchiveJobStatus.SUCCESS if external_status == "success" else ArchiveJobStatus.FAILED
        job.error_message = "" if external_status == "success" else remark
        job.finished_at = executed_at
        await ArchiveService._sync_workflow_execution_decision(
            db,
            job,
            operator,
            mode="external",
            status=WorkflowStatus.FINISH if external_status == "success" else WorkflowStatus.EXCEPTION,
            external_executed_at=executed_at,
            external_status=external_status,
            external_remark=remark,
        )
        await ArchiveService._write_execution_log(
            db, job, operator, OP_EXECUTE, f"DBA 登记归档外部已执行，结果：{external_status}，备注：{remark}"
        )
        await db.commit()
        await db.refresh(job)
        return {"msg": "外部执行结果已登记", "job_id": job.id, "workflow_id": job.workflow_id, "status": job.status}

    @staticmethod
    async def set_job_control_state(db: AsyncSession, job_id: int, action: str, operator: dict) -> ArchiveJob:
        job = await ArchiveService.get_job_obj(db, job_id)

        if action == "pause":
            src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
            ArchiveService._assert_archive_execute_scope(job, src_inst, operator)
            if job.status not in (ArchiveJobStatus.QUEUED, ArchiveJobStatus.RUNNING):
                raise AppException("只有队列中或执行中的作业可以暂停", code=400)
            job.status = ArchiveJobStatus.PAUSING
        elif action == "resume":
            src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
            ArchiveService._assert_archive_execute_scope(job, src_inst, operator)
            if job.status != ArchiveJobStatus.PAUSED:
                raise AppException("只有已暂停的作业可以继续", code=400)
            job.status = ArchiveJobStatus.QUEUED
        elif action == "cancel":
            if job.status == ArchiveJobStatus.PENDING_REVIEW:
                if not job.workflow_id:
                    if operator.get("id") != job.created_by_id and not operator.get("is_superuser"):
                        raise AppException("只能取消自己提交的归档申请", code=403)
                    job.status = ArchiveJobStatus.CANCELED
                    job.finished_at = datetime.now(UTC)
                    await db.commit()
                    await db.refresh(job)
                    return job
                await AuditService.operate(
                    db,
                    workflow_id=job.workflow_id,
                    action="cancel",
                    operator=operator,
                    remark="提交人/超管取消归档申请",
                )
                await db.refresh(job)
                return job
            if job.status in (
                ArchiveJobStatus.APPROVED,
                ArchiveJobStatus.SCHEDULED,
                ArchiveJobStatus.QUEUED,
                ArchiveJobStatus.RUNNING,
                ArchiveJobStatus.PAUSING,
                ArchiveJobStatus.PAUSED,
            ):
                src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
                ArchiveService._assert_archive_execute_scope(job, src_inst, operator)
                job.status = ArchiveJobStatus.CANCELING if job.status in (ArchiveJobStatus.RUNNING, ArchiveJobStatus.PAUSING) else ArchiveJobStatus.CANCELED
                job.finished_at = datetime.now(UTC) if job.status == ArchiveJobStatus.CANCELED else None
                if job.workflow_id and job.status == ArchiveJobStatus.CANCELED:
                    wf = await db.get(SqlWorkflow, job.workflow_id)
                    if wf and wf.status in (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.REVIEW_PASS, WorkflowStatus.TIMING_TASK, WorkflowStatus.QUEUING):
                        wf.status = WorkflowStatus.ABORT
            else:
                raise AppException("当前作业状态不能取消", code=400)
        else:
            raise AppException(f"不支持的操作：{action}", code=400)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def list_jobs(db: AsyncSession, user: dict, page: int = 1, page_size: int = 20) -> tuple[int, list[dict]]:
        conditions = []
        if not user.get("is_superuser") and not (
            "archive_review" in user.get("permissions", []) or "archive_execute" in user.get("permissions", [])
        ):
            visible_workflow_ids = await ArchiveService._visible_workflow_ids_for_user(db, user)
            visibility_conditions = [ArchiveJob.created_by_id == user.get("id")]
            if visible_workflow_ids:
                visibility_conditions.append(ArchiveJob.workflow_id.in_(visible_workflow_ids))
            conditions.append(or_(*visibility_conditions))
        count_stmt = select(func.count()).select_from(ArchiveJob).where(and_(*conditions)) if conditions else select(func.count()).select_from(ArchiveJob)
        total = int((await db.execute(count_stmt)).scalar() or 0)
        stmt = select(ArchiveJob).order_by(ArchiveJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        rows = (await db.execute(stmt)).scalars().all()
        creator_ids = {job.created_by_id for job in rows if job.created_by_id}
        creator_display_map: dict[int, str] = {}
        if creator_ids:
            creator_rows = await db.execute(
                select(Users.id, Users.username, Users.display_name).where(Users.id.in_(creator_ids))
            )
            creator_display_map = {
                user_id: (display_name or username)
                for user_id, username, display_name in creator_rows.all()
            }
        items = []
        for job in rows:
            item = ArchiveService.fmt_job(job, creator_display_map.get(job.created_by_id))
            item["can_cancel"] = await ArchiveService.can_cancel_application(db, job, user)
            item["can_audit"] = await ArchiveService.can_audit_job(db, job, user)
            item["can_execute"] = await ArchiveService.can_execute_job(db, job, user)
            item["can_control"] = await ArchiveService.can_control_job(db, job, user)
            items.append(item)
        return total, items

    @staticmethod
    async def can_audit_job(db: AsyncSession, job: ArchiveJob, user: dict) -> bool:
        if not job.workflow_id:
            return False
        wf = await db.get(SqlWorkflow, job.workflow_id)
        if not wf or wf.status != WorkflowStatus.PENDING_REVIEW:
            return False
        audit_info = await AuditService.get_audit_info(db, job.workflow_id)
        current_node = next(
            (node for node in (audit_info.get("nodes", []) if audit_info else []) if node.get("status") == 0),
            None,
        )
        if not current_node:
            return False
        try:
            await AuditService._check_approver_permission(db, user, current_node)
            return True
        except AppException:
            return False

    @staticmethod
    async def can_execute_job(db: AsyncSession, job: ArchiveJob, user: dict) -> bool:
        if job.status not in (ArchiveJobStatus.APPROVED, ArchiveJobStatus.PAUSED, ArchiveJobStatus.SCHEDULED):
            return False
        try:
            src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
            ArchiveService._assert_archive_execute_scope(job, src_inst, user)
            return True
        except AppException:
            return False

    @staticmethod
    async def can_control_job(db: AsyncSession, job: ArchiveJob, user: dict) -> bool:
        if job.status not in (
            ArchiveJobStatus.APPROVED,
            ArchiveJobStatus.SCHEDULED,
            ArchiveJobStatus.QUEUED,
            ArchiveJobStatus.RUNNING,
            ArchiveJobStatus.PAUSING,
            ArchiveJobStatus.PAUSED,
        ):
            return False
        try:
            src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
            ArchiveService._assert_archive_execute_scope(job, src_inst, user)
            return True
        except AppException:
            return False

    @staticmethod
    async def get_job_obj(db: AsyncSession, job_id: int) -> ArchiveJob:
        result = await db.execute(select(ArchiveJob).options(selectinload(ArchiveJob.batches)).where(ArchiveJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundException(f"归档作业 ID={job_id} 不存在")
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: int, user: dict) -> dict:
        job = await ArchiveService.get_job_obj(db, job_id)
        if not await ArchiveService.can_view_job(db, job, user):
            raise AppException("没有查看该归档作业的权限", code=403)
        creator_display = None
        if job.created_by_id:
            creator = await db.get(Users, job.created_by_id)
            if creator:
                creator_display = creator.display_name or creator.username
        data = ArchiveService.fmt_job(job, creator_display)
        data["can_cancel"] = await ArchiveService.can_cancel_application(db, job, user)
        data["can_audit"] = await ArchiveService.can_audit_job(db, job, user)
        data["can_execute"] = await ArchiveService.can_execute_job(db, job, user)
        data["can_control"] = await ArchiveService.can_control_job(db, job, user)
        data["batches"] = [
            {
                "id": b.id,
                "batch_no": b.batch_no,
                "status": b.status,
                "selected_rows": b.selected_rows,
                "inserted_rows": b.inserted_rows,
                "deleted_rows": b.deleted_rows,
                "message": b.message,
                "started_at": b.started_at.isoformat() if b.started_at else None,
                "finished_at": b.finished_at.isoformat() if b.finished_at else None,
            }
            for b in sorted(job.batches, key=lambda item: item.batch_no)
        ]
        return data

    @staticmethod
    async def _visible_workflow_ids_for_user(db: AsyncSession, user: dict) -> set[int]:
        pending_ids = await AuditService.get_pending_workflow_ids_for_user(db, user)
        audited_ids = await AuditService.get_audited_workflow_ids_for_user(db, user)
        return pending_ids | audited_ids

    @staticmethod
    async def can_view_job(db: AsyncSession, job: ArchiveJob, user: dict) -> bool:
        if (
            user.get("is_superuser")
            or "archive_review" in user.get("permissions", [])
            or "archive_execute" in user.get("permissions", [])
            or user.get("id") == job.created_by_id
        ):
            return True
        if not job.workflow_id:
            return False
        visible_workflow_ids = await ArchiveService._visible_workflow_ids_for_user(db, user)
        return job.workflow_id in visible_workflow_ids

    @staticmethod
    def fmt_job(job: ArchiveJob, created_by_display: str | None = None) -> dict:
        return {
            "id": job.id,
            "workflow_id": job.workflow_id,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "archive_mode": job.archive_mode,
            "source_instance_id": job.source_instance_id,
            "source_db": job.source_db,
            "source_table": job.source_table,
            "condition": job.condition,
            "dest_instance_id": job.dest_instance_id,
            "dest_db": job.dest_db,
            "dest_table": job.dest_table,
            "batch_size": job.batch_size,
            "sleep_ms": job.sleep_ms,
            "estimated_rows": job.estimated_rows,
            "processed_rows": job.processed_rows,
            "current_batch": job.current_batch,
            "row_count_is_estimated": job.row_count_is_estimated,
            "apply_reason": job.apply_reason,
            "risk_level": job.risk_level,
            "risk_summary": job.risk_summary,
            "risk_remark": job.risk_remark,
            "risk_plan": json.loads(job.risk_plan or "null") if job.risk_plan else None,
            "error_message": job.error_message,
            "created_by": job.created_by,
            "created_by_display": created_by_display or job.created_by,
            "created_by_id": job.created_by_id,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "can_cancel": False,
            "can_execute": False,
            "can_control": False,
        }

    @staticmethod
    async def can_cancel_application(db: AsyncSession, job: ArchiveJob, user: dict) -> bool:
        if job.status != ArchiveJobStatus.PENDING_REVIEW:
            return False
        if not job.workflow_id:
            return bool(user.get("is_superuser") or user.get("id") == job.created_by_id)
        wf = await db.get(SqlWorkflow, job.workflow_id)
        if not wf:
            return False
        audit_result = await db.execute(select(WorkflowAudit).where(WorkflowAudit.workflow_id == job.workflow_id))
        audit = audit_result.scalar_one_or_none()
        nodes = ApplicationCancelPolicy.load_nodes(audit.audit_auth_groups_info if audit else "")
        return ApplicationCancelPolicy.can_cancel_before_approval(
            applicant_username=wf.engineer,
            operator=user,
            status=wf.status,
            pending_status=WorkflowStatus.PENDING_REVIEW,
            nodes=nodes,
        )

    @staticmethod
    async def mark_workflow_approved(db: AsyncSession, workflow_id: int) -> None:
        result = await db.execute(select(ArchiveJob).where(ArchiveJob.workflow_id == workflow_id))
        job = result.scalar_one_or_none()
        if job and job.status == ArchiveJobStatus.PENDING_REVIEW:
            job.status = ArchiveJobStatus.APPROVED

    @staticmethod
    async def mark_workflow_canceled(db: AsyncSession, workflow_id: int) -> None:
        result = await db.execute(select(ArchiveJob).where(ArchiveJob.workflow_id == workflow_id))
        job = result.scalar_one_or_none()
        if job and job.status in (
            ArchiveJobStatus.PENDING_REVIEW,
            ArchiveJobStatus.APPROVED,
            ArchiveJobStatus.SCHEDULED,
            ArchiveJobStatus.QUEUED,
        ):
            job.status = ArchiveJobStatus.CANCELED
            job.finished_at = datetime.now(UTC)

    @staticmethod
    async def execute_job(db: AsyncSession, job_id: int, operator_id: int) -> None:
        job = await ArchiveService.get_job_obj(db, job_id)
        if job.status not in (ArchiveJobStatus.QUEUED, ArchiveJobStatus.PAUSED):
            return
        job.status = ArchiveJobStatus.RUNNING
        job.started_at = job.started_at or datetime.now(UTC)
        if job.workflow_id:
            wf = await db.get(SqlWorkflow, job.workflow_id)
            if wf:
                wf.status = WorkflowStatus.EXECUTING
        await db.commit()
        try:
            if job.archive_mode == "purge":
                await ArchiveService._execute_purge_job(db, job)
            else:
                await ArchiveService._execute_dest_job(db, job)
        except Exception as exc:
            job.status = ArchiveJobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
        finally:
            if job.workflow_id:
                wf = await db.get(SqlWorkflow, job.workflow_id)
                if wf:
                    if job.status == ArchiveJobStatus.SUCCESS:
                        wf.status = WorkflowStatus.FINISH
                    elif job.status == ArchiveJobStatus.CANCELED:
                        wf.status = WorkflowStatus.ABORT
                    else:
                        wf.status = WorkflowStatus.EXCEPTION
                    wf.finish_time = job.finished_at
                    if wf.content:
                        wf.content.execute_result = json.dumps(
                            {
                                "mode": wf.execute_mode or "immediate",
                                "success": job.status == ArchiveJobStatus.SUCCESS,
                                "status": job.status,
                                "processed_rows": job.processed_rows,
                                "current_batch": job.current_batch,
                                "error": job.error_message,
                            },
                            ensure_ascii=False,
                        )
            await db.commit()

    @staticmethod
    async def dispatch_scheduled_jobs(db: AsyncSession, limit: int = 50) -> int:
        stmt = (
            select(ArchiveJob)
            .where(
                ArchiveJob.status == ArchiveJobStatus.SCHEDULED,
                ArchiveJob.workflow_id.is_not(None),
            )
            .order_by(ArchiveJob.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        jobs = result.scalars().all()
        due_jobs: list[ArchiveJob] = []
        now = datetime.now(UTC)
        for job in jobs:
            wf = await db.get(SqlWorkflow, job.workflow_id) if job.workflow_id else None
            if not wf or not wf.scheduled_execute_at:
                continue
            scheduled_at = ArchiveService._ensure_aware_utc(wf.scheduled_execute_at)
            if scheduled_at <= now:
                job.status = ArchiveJobStatus.QUEUED
                wf.status = WorkflowStatus.QUEUING
                due_jobs.append(job)
        await db.commit()

        from app.tasks.archive import execute_archive_job_task

        dispatched = 0
        for job in due_jobs:
            wf = await db.get(SqlWorkflow, job.workflow_id) if job.workflow_id else None
            operator_id = wf.executed_by_id if wf and wf.executed_by_id else job.created_by_id
            task = execute_archive_job_task.delay(job.id, operator_id)
            job.celery_task_id = task.id
            dispatched += 1
        await db.commit()
        return dispatched

    @staticmethod
    async def _post_batch_control(db: AsyncSession, job: ArchiveJob) -> bool:
        await db.refresh(job)
        if job.status == ArchiveJobStatus.PAUSING:
            job.status = ArchiveJobStatus.PAUSED
            await db.commit()
            return False
        if job.status == ArchiveJobStatus.CANCELING:
            job.status = ArchiveJobStatus.CANCELED
            job.finished_at = datetime.now(UTC)
            await db.commit()
            return False
        return True

    @staticmethod
    async def _execute_purge_job(db: AsyncSession, job: ArchiveJob) -> None:
        inst = await ArchiveService._load_instance(db, job.source_instance_id)
        validate_archive_condition(inst.db_type, job.source_table, job.condition)
        engine = get_engine(inst)

        if inst.db_type == "mongo":
            await ArchiveService._execute_purge_mongo(db, job, engine)
            return
        if inst.db_type in ("clickhouse", "starrocks"):
            await ArchiveService._execute_single_delete(db, job, engine, inst.db_type)
            return

        delete_sql = build_batch_delete_sql(inst.db_type, job.source_table, job.condition, job.batch_size)
        for _ in range(10000):
            batch_no = job.current_batch + 1
            started = datetime.now(UTC)
            rs = await engine.execute(db_name=job.source_db, sql=delete_sql)
            if rs.error:
                await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.FAILED, 0, 0, 0, rs.error, started)
                raise AppException(f"第 {batch_no} 批执行失败：{rs.error}", code=500)
            deleted, estimated = ArchiveService._review_affected_rows(rs, min(job.batch_size, max(job.estimated_rows - job.processed_rows, 0)))
            job.current_batch = batch_no
            job.processed_rows += deleted
            job.row_count_is_estimated = job.row_count_is_estimated or estimated
            await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.SUCCESS, deleted, 0, deleted, "", started)
            await db.commit()
            if deleted <= 0 or deleted < job.batch_size or job.processed_rows >= job.estimated_rows:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            if not await ArchiveService._post_batch_control(db, job):
                return
            if job.sleep_ms > 0:
                await asyncio.sleep(job.sleep_ms / 1000)

        raise AppException("归档超过最大批次数限制", code=500)

    @staticmethod
    async def _execute_single_delete(db: AsyncSession, job: ArchiveJob, engine: Any, db_type: str) -> None:
        started = datetime.now(UTC)
        sql = build_batch_delete_sql(db_type, job.source_table, job.condition, job.batch_size)
        rs = await engine.execute(db_name=job.source_db, sql=sql)
        if rs.error:
            await ArchiveService._log_batch(db, job, job.current_batch + 1, ArchiveBatchStatus.FAILED, 0, 0, 0, rs.error, started)
            raise AppException(rs.error, code=500)
        affected, estimated = ArchiveService._review_affected_rows(rs, job.estimated_rows)
        job.current_batch += 1
        job.processed_rows += affected
        job.row_count_is_estimated = job.row_count_is_estimated or estimated
        job.status = ArchiveJobStatus.SUCCESS
        job.finished_at = datetime.now(UTC)
        await ArchiveService._log_batch(db, job, job.current_batch, ArchiveBatchStatus.SUCCESS, affected, 0, affected, "", started)

    @staticmethod
    async def _execute_purge_mongo(db: AsyncSession, job: ArchiveJob, engine: Any) -> None:
        filter_dict = json.loads(job.condition)
        client = await engine.get_connection(job.source_db)
        col = client[job.source_db][job.source_table]
        for _ in range(10000):
            batch_no = job.current_batch + 1
            started = datetime.now(UTC)
            ids = [doc["_id"] async for doc in col.find(filter_dict, {"_id": 1}).limit(job.batch_size)]
            if not ids:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            result = await col.delete_many({"_id": {"$in": ids}})
            deleted = int(result.deleted_count)
            job.current_batch = batch_no
            job.processed_rows += deleted
            await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.SUCCESS, len(ids), 0, deleted, "", started)
            await db.commit()
            if deleted < job.batch_size:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            if not await ArchiveService._post_batch_control(db, job):
                return
            if job.sleep_ms > 0:
                await asyncio.sleep(job.sleep_ms / 1000)

    @staticmethod
    async def _execute_dest_job(db: AsyncSession, job: ArchiveJob) -> None:
        src_inst = await ArchiveService._load_instance(db, job.source_instance_id)
        dest_inst = await ArchiveService._load_instance(db, job.dest_instance_id or 0)
        validate_archive_condition(src_inst.db_type, job.source_table, job.condition)
        if src_inst.db_type == "mongo":
            await ArchiveService._execute_dest_mongo(db, job, get_engine(src_inst), get_engine(dest_inst))
            return
        if src_inst.db_type not in ("mysql", "tidb", "pgsql", "oracle", "mssql"):
            raise AppException(f"{src_inst.db_type} 的 dest 模式暂不支持", code=400)

        src_engine = get_engine(src_inst)
        dest_engine = get_engine(dest_inst)
        select_sql, delete_sql = ArchiveService._build_dest_batch_sql(src_inst.db_type, job)
        for _ in range(10000):
            batch_no = job.current_batch + 1
            started = datetime.now(UTC)
            rs = await src_engine.query(db_name=job.source_db, sql=select_sql, limit_num=job.batch_size)
            if rs.error:
                await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.FAILED, 0, 0, 0, rs.error, started)
                raise AppException(rs.error, code=500)
            if not rs.rows:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            insert_sql = ArchiveService._build_insert_sql(dest_inst.db_type, job.dest_table, rs.column_list, rs.rows)
            insert_rs = await dest_engine.execute(db_name=job.dest_db, sql=insert_sql)
            if insert_rs.error:
                await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.FAILED, len(rs.rows), 0, 0, insert_rs.error, started)
                raise AppException(f"第 {batch_no} 批插入失败：{insert_rs.error}", code=500)
            del_rs = await src_engine.execute(db_name=job.source_db, sql=delete_sql)
            if del_rs.error:
                msg = f"第 {batch_no} 批删除源数据失败：{del_rs.error}（目标可能已插入，需人工核对）"
                await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.FAILED, len(rs.rows), len(rs.rows), 0, msg, started)
                raise AppException(msg, code=500)
            deleted, estimated = ArchiveService._review_affected_rows(del_rs, len(rs.rows))
            job.current_batch = batch_no
            job.processed_rows += deleted
            job.row_count_is_estimated = job.row_count_is_estimated or estimated
            await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.SUCCESS, len(rs.rows), len(rs.rows), deleted, "", started)
            await db.commit()
            if len(rs.rows) < job.batch_size:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            if not await ArchiveService._post_batch_control(db, job):
                return
            if job.sleep_ms > 0:
                await asyncio.sleep(job.sleep_ms / 1000)

    @staticmethod
    async def _execute_dest_mongo(db: AsyncSession, job: ArchiveJob, src_engine: Any, dest_engine: Any) -> None:
        filter_dict = json.loads(job.condition)
        src = (await src_engine.get_connection(job.source_db))[job.source_db][job.source_table]
        dest = (await dest_engine.get_connection(job.dest_db))[job.dest_db][job.dest_table]
        for _ in range(10000):
            batch_no = job.current_batch + 1
            started = datetime.now(UTC)
            docs = await src.find(filter_dict).limit(job.batch_size).to_list(job.batch_size)
            if not docs:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            await dest.insert_many(docs)
            ids = [doc["_id"] for doc in docs]
            result = await src.delete_many({"_id": {"$in": ids}})
            deleted = int(result.deleted_count)
            job.current_batch = batch_no
            job.processed_rows += deleted
            await ArchiveService._log_batch(db, job, batch_no, ArchiveBatchStatus.SUCCESS, len(docs), len(docs), deleted, "", started)
            await db.commit()
            if len(docs) < job.batch_size:
                job.status = ArchiveJobStatus.SUCCESS
                job.finished_at = datetime.now(UTC)
                await db.commit()
                return
            if not await ArchiveService._post_batch_control(db, job):
                return
            if job.sleep_ms > 0:
                await asyncio.sleep(job.sleep_ms / 1000)

    @staticmethod
    def _build_dest_batch_sql(db_type: str, job: ArchiveJob) -> tuple[str, str]:
        dt = db_type.lower()
        t = _quote_identifier(dt, job.source_table)
        if dt in ("mysql", "tidb"):
            return f"SELECT * FROM {t} WHERE {job.condition} LIMIT {job.batch_size}", f"DELETE FROM {t} WHERE {job.condition} LIMIT {job.batch_size}"
        if dt == "pgsql":
            return (
                f"SELECT * FROM {t} WHERE {job.condition} LIMIT {job.batch_size}",
                f"DELETE FROM {t} WHERE ctid IN (SELECT ctid FROM {t} WHERE {job.condition} LIMIT {job.batch_size})",
            )
        if dt == "oracle":
            return (
                f"SELECT * FROM {t} WHERE {job.condition} AND ROWNUM <= {job.batch_size}",
                f"DELETE FROM {t} WHERE ROWID IN (SELECT ROWID FROM {t} WHERE {job.condition} AND ROWNUM <= {job.batch_size})",
            )
        if dt == "mssql":
            return f"SELECT TOP {job.batch_size} * FROM {t} WHERE {job.condition}", f"DELETE TOP({job.batch_size}) FROM {t} WHERE {job.condition}"
        raise AppException(f"{db_type} 的 dest 模式暂不支持", code=400)

    @staticmethod
    def _build_insert_sql(db_type: str, table: str, columns: list[str], rows: list[Any]) -> str:
        cols = ", ".join(_quote_identifier(db_type, col) for col in columns)
        values = []
        for row in rows:
            row_values = [row.get(col) for col in columns] if isinstance(row, dict) else list(row)
            parts = []
            for value in row_values:
                if value is None:
                    parts.append("NULL")
                else:
                    parts.append("'" + str(value).replace("'", "''") + "'")
            values.append("(" + ", ".join(parts) + ")")
        return f"INSERT INTO {_quote_identifier(db_type, table)} ({cols}) VALUES " + ", ".join(values)

    @staticmethod
    async def _log_batch(
        db: AsyncSession,
        job: ArchiveJob,
        batch_no: int,
        status: ArchiveBatchStatus,
        selected_rows: int,
        inserted_rows: int,
        deleted_rows: int,
        message: str,
        started_at: datetime,
    ) -> None:
        db.add(
            ArchiveBatchLog(
                job_id=job.id,
                batch_no=batch_no,
                status=status,
                selected_rows=selected_rows,
                inserted_rows=inserted_rows,
                deleted_rows=deleted_rows,
                message=message,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )
