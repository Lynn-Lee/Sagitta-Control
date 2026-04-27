"""
SQL 工单业务逻辑服务（Sprint 3）。
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.user import Users
from app.models.workflow import (
    SqlWorkflow,
    SqlWorkflowContent,
    WorkflowAudit,
    WorkflowStatus,
    WorkflowType,
)
from app.schemas.workflow import WorkflowCreateRequest, WorkflowExecuteRequest
from app.services.audit import OP_EXECUTE, OP_TIMING, AuditService
from app.services.cancel_policy import ApplicationCancelPolicy
from app.services.governance_scope import GovernanceScopeService
from app.services.risk_plan import RiskPlanService

logger = logging.getLogger(__name__)

HIGH_RISK_SQL_SUBMIT_PERMISSION = "sql_submit_high_risk"
HIGH_RISK_SQL_SUBMIT_ROLES = {"dba", "dba_group"}

STATUS_DESC = {
    0: "待审核",
    1: "审批驳回",       # 人工驳回（原 AUTO_REVIEW_FAIL 复用）
    2: "审核通过",
    3: "定时执行",
    4: "队列中",
    5: "执行中",
    6: "执行成功",
    7: "执行异常",
    8: "已取消",         # 人工取消（原 ABORT）
    9: "自动审核不通过",  # 系统自动拒绝（预留，与人工驳回区分）
}

WORKFLOW_TYPE_LABEL = {
    int(WorkflowType.QUERY): "查询权限",
    int(WorkflowType.SQL): "SQL 工单",
    int(WorkflowType.ARCHIVE): "数据归档",
    int(WorkflowType.MONITOR): "监控权限",
}

EXECUTION_RECORD_STATUSES = (
    WorkflowStatus.REVIEW_PASS,
    WorkflowStatus.TIMING_TASK,
    WorkflowStatus.QUEUING,
    WorkflowStatus.EXECUTING,
    WorkflowStatus.FINISH,
    WorkflowStatus.EXCEPTION,
)


class WorkflowService:
    @staticmethod
    def _can_cancel_workflow(wf: SqlWorkflow, user: dict, nodes: list[dict] | None = None) -> bool:
        return ApplicationCancelPolicy.can_cancel_before_approval(
            applicant_username=wf.engineer,
            operator=user,
            status=wf.status,
            pending_status=WorkflowStatus.PENDING_REVIEW,
            nodes=nodes or [],
        )

    @staticmethod
    def _can_submit_high_risk_sql(operator: dict) -> bool:
        return bool(
            operator.get("is_superuser")
            or operator.get("role") in HIGH_RISK_SQL_SUBMIT_ROLES
            or HIGH_RISK_SQL_SUBMIT_PERMISSION in operator.get("permissions", [])
        )

    @staticmethod
    def _build_audit_chain_text(
        nodes: list[dict],
        workflow_status: int,
        operator_display_map: dict[str, str] | None = None,
    ) -> str:
        if not nodes:
            return "—"
        if workflow_status == WorkflowStatus.PENDING_REVIEW:
            return " -> ".join(
                str(node.get("node_name") or f"第{node.get('order', '?')}级审批") for node in nodes
            )

        operator_display_map = operator_display_map or {}
        actor_chain: list[str] = []
        for node in nodes:
            operator = (node.get("operator") or "").strip()
            if operator:
                actor_chain.append(operator_display_map.get(operator, operator))

        return " -> ".join(actor_chain) if actor_chain else "—"

    @staticmethod
    def _get_current_node_name(nodes: list[dict], workflow_status: int) -> str:
        if workflow_status != WorkflowStatus.PENDING_REVIEW:
            return "—"
        current_node = next((node for node in nodes if node.get("status") == 0), None)
        return current_node.get("node_name", "—") if current_node else "—"

    @staticmethod
    def _decorate_snapshot_for_applicant(nodes_snapshot: list[dict], applicant: dict) -> list[dict]:
        result: list[dict] = []
        for node in nodes_snapshot:
            node_copy = dict(node)
            if node_copy.get("approver_type") == "manager":
                node_copy["applicant_id"] = applicant.get("id")
                node_copy["applicant_name"] = applicant.get("display_name") or applicant.get("username")
            result.append(node_copy)
        return result

    @staticmethod
    def _fmt_workflow(wf: SqlWorkflow, instance_name: str = "") -> dict:
        """序列化工单为 dict（不含 SQL 内容）。"""
        risk_level = ""
        risk_summary = ""
        content = getattr(wf, "content", None)
        if content and getattr(content, "risk_plan", ""):
            try:
                risk_plan = json.loads(content.risk_plan)
                risk_level = risk_plan.get("level", "") or ""
                risk_summary = risk_plan.get("summary", "") or ""
            except (TypeError, ValueError):
                risk_level = ""
                risk_summary = ""
        return {
            "id": wf.id,
            "workflow_name": wf.workflow_name,
            "group_id": wf.group_id,
            "group_name": wf.group_name,
            "instance_id": wf.instance_id,
            "instance_name": instance_name,      # 目标实例名称
            "db_name": wf.db_name,
            "syntax_type": wf.syntax_type,
            "is_backup": wf.is_backup,
            "engineer": wf.engineer,
            "engineer_display": wf.engineer_display,
            "status": wf.status,
            "status_desc": STATUS_DESC.get(wf.status, "未知"),
            "workflow_type": int(WorkflowType.SQL),
            "workflow_type_label": WORKFLOW_TYPE_LABEL[int(WorkflowType.SQL)],
            "audit_auth_groups": wf.audit_auth_groups,
            "run_date_start": wf.run_date_start.isoformat() if wf.run_date_start else None,
            "run_date_end": wf.run_date_end.isoformat() if wf.run_date_end else None,
            "execute_mode": getattr(wf, "execute_mode", None),
            "scheduled_execute_at": (
                wf.scheduled_execute_at.isoformat() if getattr(wf, "scheduled_execute_at", None) else None
            ),
            "executed_by_id": getattr(wf, "executed_by_id", None),
            "executed_by_name": getattr(wf, "executed_by_name", None),
            "external_executed_at": (
                wf.external_executed_at.isoformat() if getattr(wf, "external_executed_at", None) else None
            ),
            "external_result_status": getattr(wf, "external_result_status", None),
            "external_result_remark": getattr(wf, "external_result_remark", None),
            "finish_time": wf.finish_time.isoformat() if wf.finish_time else None,
            "created_at": wf.created_at.isoformat() if wf.created_at else "",
            "current_node_name": "—",
            "audit_chain_text": "—",
            "risk_level": risk_level,
            "risk_summary": risk_summary,
            "risk_remark": getattr(content, "risk_remark", "") if content else "",
        }

    # ── 创建工单 ──────────────────────────────────────────────

    @staticmethod
    async def create(
        db: AsyncSession,
        data: WorkflowCreateRequest,
        operator: dict,
    ) -> SqlWorkflow:
        if data.flow_id is None:
            raise AppException("请选择审批流", code=400)
        # 加载实例
        inst_result = await db.execute(
            select(Instance)
            .options(selectinload(Instance.resource_groups))
            .where(Instance.id == data.instance_id)
        )
        inst = inst_result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={data.instance_id} 不存在")

        # v2-lite：资源组由“用户可访问的资源组 ∩ 实例所属资源组”自动解析
        user_rg_ids = set(operator.get("resource_groups", []))
        instance_rgs = [rg for rg in inst.resource_groups if rg.is_active]
        matched_rgs = [rg for rg in instance_rgs if rg.id in user_rg_ids]

        if data.group_id is not None:
            matched_rgs = [rg for rg in matched_rgs if rg.id == data.group_id]
            if not matched_rgs:
                raise AppException("所选资源组不在你的实例访问范围内", code=400)

        if not matched_rgs:
            raise AppException("目标实例不在你的资源组访问范围内，无法提交工单", code=403)

        rg = sorted(matched_rgs, key=lambda item: item.id)[0]
        audit_auth_groups = str(rg.id)

        # 如果指定了审批流模板，生成节点快照
        nodes_snapshot: list[dict] | None = None
        if data.flow_id:
            from app.services.approval_flow import ApprovalFlowService
            nodes_snapshot = await ApprovalFlowService.snapshot_for_workflow(db, data.flow_id)
            nodes_snapshot = WorkflowService._decorate_snapshot_for_applicant(nodes_snapshot, operator)

        db_type = getattr(inst, "db_type", "") or ""
        risk_plan = RiskPlanService.build_workflow_plan(db_type, data.db_name, data.sql_content)
        is_privileged_high_risk_sql = (
            risk_plan.level == "high"
            and RiskPlanService.is_privileged_workflow_sql(db_type, data.sql_content)
        )
        can_submit_high_risk_sql = WorkflowService._can_submit_high_risk_sql(operator)

        # 自动 SQL 预检查
        engine = get_engine(inst)
        review_set = await engine.execute_check(data.db_name, data.sql_content)
        review_json = json.dumps(
            [{"sql": item.sql, "errlevel": item.errlevel, "msg": item.errormessage}
             for item in (review_set.rows if hasattr(review_set, 'rows') else [])],
            ensure_ascii=False
        )

        # 如果有严重错误，拒绝提交
        review_error = getattr(review_set, "error", "") or ""
        if review_error:
            raise AppException(f"SQL 预检查失败：{review_error}", code=400)

        error_count = getattr(review_set, 'error_count', 0)
        if error_count > 0:
            if not (is_privileged_high_risk_sql and can_submit_high_risk_sql):
                if is_privileged_high_risk_sql:
                    raise AppException("高危 SQL 工单需要高危提交权限，请联系 DBA 提交或申请权限", code=403)
                raise AppException("SQL 预检查不通过，请修改后重新提交", code=400)

        if is_privileged_high_risk_sql and not can_submit_high_risk_sql:
            raise AppException("高危 SQL 工单需要高危提交权限，请联系 DBA 提交或申请权限", code=403)

        if risk_plan.requires_manual_remark and not (data.risk_remark or "").strip():
            raise AppException("高风险工单必须填写风险/回滚说明", code=400)

        # 创建工单主记录
        workflow = SqlWorkflow(
            workflow_name=data.workflow_name,
            group_id=rg.id,
            group_name=rg.group_name,
            instance_id=data.instance_id,
            db_name=data.db_name,
            syntax_type=data.syntax_type,
            is_backup=data.is_backup,
            engineer=operator.get("username", ""),
            engineer_display=operator.get("display_name", ""),
            engineer_id=operator.get("id", 0),
            status=WorkflowStatus.PENDING_REVIEW,
            audit_auth_groups=audit_auth_groups,
            flow_id=data.flow_id,
            run_date_start=data.run_date_start,
            run_date_end=data.run_date_end,
        )
        db.add(workflow)
        await db.flush()

        # 创建内容记录
        content = SqlWorkflowContent(
            workflow_id=workflow.id,
            sql_content=data.sql_content,
            review_content=review_json,
            execute_result="",
            risk_plan=json.dumps(risk_plan.model_dump(), ensure_ascii=False),
            risk_remark=data.risk_remark or "",
        )
        db.add(content)
        await db.flush()

        # 创建审批记录
        audit_svc = AuditService(workflow=workflow)
        await audit_svc.create_audit(db, operator, nodes_snapshot=nodes_snapshot)

        logger.info("workflow_created: id=%s name=%s", workflow.id, data.workflow_name)
        return workflow

    # ── 查询工单列表 ──────────────────────────────────────────

    @staticmethod
    async def list_workflows(
        db: AsyncSession,
        user: dict,
        view: str = "mine",
        status: int | None = None,
        instance_id: int | None = None,
        search: str | None = None,
        engineer: str | None = None,
        db_name: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict], dict | None]:
        """
        查询工单列表。
        所有过滤条件均通过同一套 WHERE 子句构建，避免条件不一致问题。
        """
        from datetime import datetime, timedelta

        # ── 构建通用 WHERE 条件列表 ────────────────────────────
        conditions = []

        from app.services.audit import AuditService

        scope: dict | None = None
        if view == "mine":
            conditions.append(SqlWorkflow.engineer_id == user["id"])
        elif view == "audit":
            pending_ids = await AuditService.get_pending_workflow_ids_for_user(db, user)
            audited_ids = await AuditService.get_audited_workflow_ids_for_user(db, user)
            related_ids = pending_ids | audited_ids
            if related_ids:
                conditions.append(SqlWorkflow.id.in_(related_ids))
            else:
                conditions.append(SqlWorkflow.id == -1)
        elif view == "execute":
            conditions.append(SqlWorkflow.status.in_(EXECUTION_RECORD_STATUSES))
            if not user.get("is_superuser") and "sql_execute" not in user.get("permissions", []):
                conditions.append(SqlWorkflow.engineer_id == user["id"])
        elif view == "scope":
            scope = await GovernanceScopeService.resolve(db, user, "workflow")
        else:
            raise AppException("不支持的工单视图类型", code=400)

        if status is not None:
            conditions.append(SqlWorkflow.status == status)

        if instance_id:
            conditions.append(SqlWorkflow.instance_id == instance_id)

        if search:
            conditions.append(SqlWorkflow.workflow_name.ilike(f"%{search}%"))

        if engineer:
            conditions.append(
                SqlWorkflow.engineer.ilike(f"%{engineer}%") |
                SqlWorkflow.engineer_display.ilike(f"%{engineer}%")
            )

        if db_name:
            conditions.append(SqlWorkflow.db_name.ilike(f"%{db_name}%"))

        if date_start:
            try:
                ds = datetime.fromisoformat(date_start).replace(tzinfo=UTC)
                conditions.append(SqlWorkflow.created_at >= ds)
            except ValueError:
                pass

        if date_end:
            try:
                de = (datetime.fromisoformat(date_end).replace(tzinfo=UTC)
                      + timedelta(days=1))
                conditions.append(SqlWorkflow.created_at < de)
            except ValueError:
                pass

        # ── 统计总数（同一套条件）────────────────────────────
        count_stmt = select(func.count()).select_from(SqlWorkflow)
        if scope:
            count_stmt = GovernanceScopeService.apply_scope(
                count_stmt,
                scope,
                user_col=SqlWorkflow.engineer_id,
                instance_col=SqlWorkflow.instance_id,
            )
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar_one()

        # ── 查询数据（JOIN Instance 获取实例名）──────────────
        data_stmt = (
            select(SqlWorkflow, Instance.instance_name)
            .outerjoin(Instance, SqlWorkflow.instance_id == Instance.id)
            .options(selectinload(SqlWorkflow.content))
        )
        if scope:
            data_stmt = GovernanceScopeService.apply_scope(
                data_stmt,
                scope,
                user_col=SqlWorkflow.engineer_id,
                instance_col=SqlWorkflow.instance_id,
            )
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))
        data_stmt = (
            data_stmt
            .order_by(SqlWorkflow.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await db.execute(data_stmt)
        rows = result.all()
        workflow_ids = [wf.id for wf, _ in rows]

        audit_map: dict[int, WorkflowAudit] = {}
        if workflow_ids:
            audit_rows = await db.execute(
                select(WorkflowAudit).where(WorkflowAudit.workflow_id.in_(workflow_ids))
            )
            audit_map = {audit.workflow_id: audit for audit in audit_rows.scalars().all()}

        operator_display_map: dict[str, str] = {}
        operator_usernames = {
            str(node.get("operator")).strip()
            for audit in audit_map.values()
            for node in json.loads(audit.audit_auth_groups_info or "[]")
            if node.get("operator")
        }
        if operator_usernames:
            user_rows = await db.execute(
                select(Users.username, Users.display_name).where(Users.username.in_(operator_usernames))
            )
            operator_display_map = {
                username: (display_name or username)
                for username, display_name in user_rows.all()
            }

        items: list[dict] = []
        for wf, inst_name in rows:
            item = WorkflowService._fmt_workflow(wf, inst_name or "")
            audit = audit_map.get(wf.id)
            if audit:
                workflow_type = int(getattr(audit, "workflow_type", None) or WorkflowType.SQL)
                item["workflow_type"] = workflow_type
                item["workflow_type_label"] = WORKFLOW_TYPE_LABEL.get(workflow_type, "SQL 工单")
            if audit and audit.audit_auth_groups_info:
                nodes = json.loads(audit.audit_auth_groups_info or "[]")
                item["current_node_name"] = WorkflowService._get_current_node_name(nodes, wf.status)
                item["audit_chain_text"] = WorkflowService._build_audit_chain_text(
                    nodes,
                    wf.status,
                    operator_display_map,
                )
            else:
                nodes = []
            item["can_cancel"] = WorkflowService._can_cancel_workflow(wf, user, nodes)
            items.append(item)
        scope_payload = {"mode": scope["mode"], "label": scope["label"]} if scope else None
        return total, items, scope_payload

        # ── 工单详情 ──────────────────────────────────────────────

    @staticmethod
    async def get_detail(db: AsyncSession, workflow_id: int, user: dict) -> dict:
        result = await db.execute(
            select(SqlWorkflow, Instance.instance_name)
            .outerjoin(Instance, SqlWorkflow.instance_id == Instance.id)
            .options(selectinload(SqlWorkflow.content))
            .where(SqlWorkflow.id == workflow_id)
        )
        row = result.first()
        if not row:
            raise NotFoundException(f"工单 ID={workflow_id} 不存在")
        wf, inst_name = row

        detail = WorkflowService._fmt_workflow(wf, inst_name or "")
        if wf.content:
            detail["sql_content"] = wf.content.sql_content
            detail["review_content"] = wf.content.review_content
            detail["execute_result"] = wf.content.execute_result
            try:
                detail["risk_plan"] = json.loads(getattr(wf.content, "risk_plan", "") or "null")
            except Exception:
                detail["risk_plan"] = None
            detail["risk_remark"] = getattr(wf.content, "risk_remark", "") or ""
        else:
            detail["sql_content"] = ""
            detail["review_content"] = ""
            detail["execute_result"] = ""
            detail["risk_plan"] = None
            detail["risk_remark"] = ""

        audit_info = await AuditService.get_audit_info(db, workflow_id)
        if audit_info:
            workflow_type = int(audit_info.get("workflow_type") or WorkflowType.SQL)
            detail["workflow_type"] = workflow_type
            detail["workflow_type_label"] = WORKFLOW_TYPE_LABEL.get(workflow_type, "SQL 工单")
        detail["audit_logs"] = await AuditService.get_audit_logs(db, workflow_id)
        detail["audit_info"] = audit_info

        current_node = None
        if audit_info:
            current_node = next(
                (node for node in audit_info.get("nodes", []) if node.get("status") == 0),
                None,
            )

        can_audit = False
        if wf.status == WorkflowStatus.PENDING_REVIEW and current_node is not None:
            try:
                await AuditService._check_approver_permission(db, user, current_node)
                can_audit = True
            except AppException:
                can_audit = False

        can_execute = (
            wf.status == WorkflowStatus.REVIEW_PASS
            and (user.get("is_superuser") or "sql_execute" in user.get("permissions", []))
        )
        can_cancel = WorkflowService._can_cancel_workflow(
            wf,
            user,
            audit_info.get("nodes", []) if audit_info else [],
        )
        detail["can_audit"] = can_audit
        detail["can_execute"] = can_execute
        detail["can_cancel"] = can_cancel
        return detail

    # ── 执行工单 ──────────────────────────────────────────────

    @staticmethod
    async def execute(
        db: AsyncSession,
        workflow_id: int,
        operator: dict,
        data: WorkflowExecuteRequest | None = None,
        mode: str | None = None,
    ) -> dict:
        if data is None:
            data = WorkflowExecuteRequest(mode=mode or "immediate")

        result = await db.execute(
            select(SqlWorkflow)
            .options(selectinload(SqlWorkflow.content))
            .where(SqlWorkflow.id == workflow_id)
        )
        wf = result.scalar_one_or_none()
        if not wf:
            raise NotFoundException(f"工单 ID={workflow_id} 不存在")

        if wf.status != WorkflowStatus.REVIEW_PASS:
            raise AppException(
                f"工单状态为【{STATUS_DESC.get(wf.status,'未知')}】，不能执行", code=400
            )

        if data.mode == "scheduled":
            return await WorkflowService._schedule_execution(db, wf, operator, data)
        if data.mode == "external":
            return await WorkflowService._record_external_execution(db, wf, operator, data)

        return await WorkflowService._execute_immediately(db, wf, operator)

    @staticmethod
    def _operator_display(operator: dict) -> str:
        return operator.get("display_name") or operator.get("username") or str(operator.get("id", ""))

    @staticmethod
    def _ensure_aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    async def _get_workflow_audit(db: AsyncSession, workflow_id: int) -> WorkflowAudit | None:
        audit_result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == workflow_id)
        )
        return audit_result.scalar_one_or_none()

    @staticmethod
    async def _write_execution_log(
        db: AsyncSession,
        workflow_id: int,
        operator: dict,
        operation_type: str,
        remark: str,
    ) -> None:
        audit = await WorkflowService._get_workflow_audit(db, workflow_id)
        if audit:
            await AuditService._write_log(db, audit.id, operator, operation_type, remark=remark)

    @staticmethod
    async def _execute_immediately(
        db: AsyncSession,
        wf: SqlWorkflow,
        operator: dict,
    ) -> dict:
        # 更新为队列中
        wf.execute_mode = "immediate"
        wf.executed_by_id = operator.get("id")
        wf.executed_by_name = WorkflowService._operator_display(operator)
        wf.scheduled_execute_at = None
        wf.status = WorkflowStatus.QUEUING
        await WorkflowService._write_execution_log(
            db,
            wf.id,
            operator,
            OP_EXECUTE,
            remark="DBA 确认立即平台执行，已加入执行队列",
        )
        await db.commit()

        # 提交 Celery 任务
        try:
            from app.tasks.execute_sql import execute_workflow_task
            task = execute_workflow_task.delay(wf.id, operator.get("id"))
            return {
                "msg": "已加入执行队列",
                "task_id": task.id,
                "workflow_id": wf.id,
            }
        except Exception as e:
            # Celery 不可用时降级为同步执行
            logger.warning("celery_unavailable, executing sync: %s", str(e))
            await WorkflowService._execute_sync(db, wf, operator)
            return {"msg": "执行完成（同步模式）", "workflow_id": wf.id}

    @staticmethod
    async def _schedule_execution(
        db: AsyncSession,
        wf: SqlWorkflow,
        operator: dict,
        data: WorkflowExecuteRequest,
    ) -> dict:
        scheduled_at = data.scheduled_at or data.timing_time
        if scheduled_at is None:
            raise AppException("请选择预约执行时间", code=400)
        scheduled_at = WorkflowService._ensure_aware_utc(scheduled_at)
        if scheduled_at <= datetime.now(UTC):
            raise AppException("预约执行时间必须晚于当前时间", code=400)

        wf.execute_mode = "scheduled"
        wf.scheduled_execute_at = scheduled_at
        wf.executed_by_id = operator.get("id")
        wf.executed_by_name = WorkflowService._operator_display(operator)
        wf.status = WorkflowStatus.TIMING_TASK
        await WorkflowService._write_execution_log(
            db,
            wf.id,
            operator,
            OP_TIMING,
            remark=f"DBA 预约平台执行，预约时间：{scheduled_at.isoformat()}",
        )
        await db.commit()
        return {
            "msg": "已预约定时执行",
            "workflow_id": wf.id,
            "scheduled_execute_at": scheduled_at.isoformat(),
        }

    @staticmethod
    async def _record_external_execution(
        db: AsyncSession,
        wf: SqlWorkflow,
        operator: dict,
        data: WorkflowExecuteRequest,
    ) -> dict:
        if data.external_executed_at is None:
            raise AppException("请填写外部实际执行时间", code=400)
        if not data.external_status:
            raise AppException("请选择外部执行结果", code=400)
        remark = (data.external_remark or "").strip()
        if not remark:
            raise AppException("请填写外部执行结果备注", code=400)

        executed_at = WorkflowService._ensure_aware_utc(data.external_executed_at)
        wf.execute_mode = "external"
        wf.executed_by_id = operator.get("id")
        wf.executed_by_name = WorkflowService._operator_display(operator)
        wf.external_executed_at = executed_at
        wf.external_result_status = data.external_status
        wf.external_result_remark = remark
        wf.finish_time = executed_at
        wf.status = WorkflowStatus.FINISH if data.external_status == "success" else WorkflowStatus.EXCEPTION
        if wf.content:
            wf.content.execute_result = json.dumps(
                {
                    "mode": "external",
                    "success": data.external_status == "success",
                    "status": data.external_status,
                    "executed_at": executed_at.isoformat(),
                    "operator": wf.executed_by_name,
                    "remark": remark,
                },
                ensure_ascii=False,
            )
        await WorkflowService._write_execution_log(
            db,
            wf.id,
            operator,
            OP_EXECUTE,
            remark=f"DBA 登记外部已执行，结果：{data.external_status}，备注：{remark}",
        )
        await db.commit()
        return {"msg": "外部执行结果已登记", "workflow_id": wf.id, "status": wf.status}

    @staticmethod
    async def _execute_sync(
        db: AsyncSession,
        wf: SqlWorkflow,
        operator: dict,
    ) -> None:
        """同步执行工单（Celery 不可用时的降级方案）。"""
        from app.models.instance import Instance
        inst_result = await db.execute(
            select(Instance).where(Instance.id == wf.instance_id)
        )
        inst = inst_result.scalar_one_or_none()
        if not inst:
            wf.status = WorkflowStatus.EXCEPTION
            await db.commit()
            return

        wf.status = WorkflowStatus.EXECUTING
        await db.commit()

        engine = get_engine(inst)
        sql = wf.content.sql_content if wf.content else ""

        try:
            review_set = await engine.execute(db_name=wf.db_name, sql=sql)
            result_json = json.dumps(
                {"success": not review_set.error, "error": review_set.error or ""},
                ensure_ascii=False
            )
            if wf.content:
                wf.content.execute_result = result_json
            wf.status = WorkflowStatus.FINISH if not review_set.error else WorkflowStatus.EXCEPTION
            wf.finish_time = datetime.now(UTC)
        except Exception as e:
            if wf.content:
                wf.content.execute_result = json.dumps({"error": str(e)})
            wf.status = WorkflowStatus.EXCEPTION
            wf.finish_time = datetime.now(UTC)

        # 写执行日志
        audit_result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == wf.id)
        )
        audit = audit_result.scalar_one_or_none()
        if audit:
            await AuditService._write_log(
                db, audit.id, operator, OP_EXECUTE,
                remark=f"执行完成，状态：{STATUS_DESC.get(wf.status,'未知')}"
            )
        await db.commit()

    # ── SQL 预检查 ────────────────────────────────────────────

    @staticmethod
    async def check_sql(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        sql_content: str,
    ) -> list[dict]:
        inst_result = await db.execute(
            select(Instance).where(Instance.id == instance_id)
        )
        inst = inst_result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")

        engine = get_engine(inst)
        review_set = await engine.execute_check(db_name, sql_content)
        rows = getattr(review_set, 'rows', [])
        return [
            {
                "id": getattr(item, 'id', i+1),
                "sql": getattr(item, 'sql', ''),
                "errlevel": getattr(item, 'errlevel', 0),
                "msg": getattr(item, 'errormessage', ''),
                "stagestatus": getattr(item, 'stagestatus', ''),
            }
            for i, item in enumerate(rows)
        ]

    # ── 待我审核 ──────────────────────────────────────────────

    @staticmethod
    async def pending_for_me(
        db: AsyncSession, user: dict, page: int = 1, page_size: int = 20
    ) -> tuple[int, list[dict]]:
        """
        获取当前用户有权限审批的工单列表。
        委托给 AuditService.get_pending_for_user 按节点权限过滤。
        """
        from app.services.audit import AuditService
        return await AuditService.get_pending_for_user(db, user, page, page_size)
