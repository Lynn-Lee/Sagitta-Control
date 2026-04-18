"""
SQL 工单业务逻辑服务（Sprint 3）。
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
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
)
from app.schemas.workflow import WorkflowCreateRequest
from app.services.audit import OP_EXECUTE, AuditService

logger = logging.getLogger(__name__)

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
            "audit_auth_groups": wf.audit_auth_groups,
            "run_date_start": wf.run_date_start.isoformat() if wf.run_date_start else None,
            "run_date_end": wf.run_date_end.isoformat() if wf.run_date_end else None,
            "finish_time": wf.finish_time.isoformat() if wf.finish_time else None,
            "created_at": wf.created_at.isoformat() if wf.created_at else "",
            "current_node_name": "—",
            "audit_chain_text": "—",
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

        # 自动 SQL 预检查
        engine = get_engine(inst)
        review_set = await engine.execute_check(data.db_name, data.sql_content)
        review_json = json.dumps(
            [{"sql": item.sql, "errlevel": item.errlevel, "msg": item.errormessage}
             for item in (review_set.rows if hasattr(review_set, 'rows') else [])],
            ensure_ascii=False
        )

        # 如果有严重错误，拒绝提交
        error_count = getattr(review_set, 'error_count', 0)
        if error_count > 0 and not review_set.error:
            raise AppException("SQL 预检查不通过，请修改后重新提交", code=400)

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
    ) -> tuple[int, list[dict]]:
        """
        查询工单列表。
        所有过滤条件均通过同一套 WHERE 子句构建，避免条件不一致问题。
        """
        from datetime import datetime, timedelta

        # ── 构建通用 WHERE 条件列表 ────────────────────────────
        conditions = []

        from app.services.audit import AuditService

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
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await db.execute(count_stmt)).scalar_one()

        # ── 查询数据（JOIN Instance 获取实例名）──────────────
        data_stmt = (
            select(SqlWorkflow, Instance.instance_name)
            .outerjoin(Instance, SqlWorkflow.instance_id == Instance.id)
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
            if audit and audit.audit_auth_groups_info:
                nodes = json.loads(audit.audit_auth_groups_info or "[]")
                item["current_node_name"] = WorkflowService._get_current_node_name(nodes, wf.status)
                item["audit_chain_text"] = WorkflowService._build_audit_chain_text(
                    nodes,
                    wf.status,
                    operator_display_map,
                )
            items.append(item)
        return total, items

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
        else:
            detail["sql_content"] = ""
            detail["review_content"] = ""
            detail["execute_result"] = ""

        audit_info = await AuditService.get_audit_info(db, workflow_id)
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
        can_cancel = (
            wf.status in (
                WorkflowStatus.PENDING_REVIEW,
                WorkflowStatus.AUTO_REVIEW_FAIL,
                WorkflowStatus.REVIEW_PASS,
                WorkflowStatus.TIMING_TASK,
            )
            and (user.get("is_superuser") or user.get("username") == wf.engineer)
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
        mode: str = "auto",
    ) -> dict:
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

        # 更新为队列中
        wf.status = WorkflowStatus.QUEUING
        await db.commit()

        # 提交 Celery 任务
        try:
            from app.tasks.execute_sql import execute_workflow_task
            task = execute_workflow_task.delay(workflow_id, operator.get("id"))
            return {
                "msg": "已加入执行队列",
                "task_id": task.id,
                "workflow_id": workflow_id,
            }
        except Exception as e:
            # Celery 不可用时降级为同步执行
            logger.warning("celery_unavailable, executing sync: %s", str(e))
            await WorkflowService._execute_sync(db, wf, operator)
            return {"msg": "执行完成（同步模式）", "workflow_id": workflow_id}

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
