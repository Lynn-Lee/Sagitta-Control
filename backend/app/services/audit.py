"""
审批流核心服务。

变更说明（多级审批升级）：
- create_audit 新增 nodes_snapshot 参数，支持从流程模板快照构建审批链；
  未传 snapshot 时保持原有逻辑（向后兼容）。
- operate 中 pass/reject 操作前增加审批人权限校验。
- _is_authorized_approver 负责按节点类型判断当前用户是否有权限审批。
- get_pending_for_user 返回当前用户有权限审批的工单列表。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.models.workflow import (
    AuditStatus,
    SqlWorkflow,
    WorkflowAudit,
    WorkflowLog,
    WorkflowStatus,
    WorkflowType,
)

logger = logging.getLogger(__name__)

# 操作类型常量
OP_SUBMIT = "submit"
OP_PASS = "pass"
OP_REJECT = "reject"
OP_CANCEL = "cancel"
OP_EXECUTE = "execute"
OP_TIMING = "timing"
OP_ABORT = "abort"


class AuditService:
    """
    审批流服务。
    支持管理员自定义多级审批链，每个节点可以配置不同的审批人范围。
    """

    def __init__(
        self,
        workflow: SqlWorkflow,
        workflow_type: WorkflowType = WorkflowType.SQL,
    ):
        self.workflow = workflow
        self.workflow_type = workflow_type

    # ── 创建审批记录 ──────────────────────────────────────────

    async def create_audit(
        self,
        db: AsyncSession,
        operator: dict,
        nodes_snapshot: list[dict] | None = None,
    ) -> WorkflowAudit:
        """
        工单提交时创建审批记录。

        nodes_snapshot 不为 None 时：使用流程模板快照（新多级审批方式）。
        nodes_snapshot 为 None 时：回退到旧逻辑，从 audit_auth_groups 字符串解析。
        """
        if nodes_snapshot is not None:
            groups_info = nodes_snapshot
            first_node = groups_info[0] if groups_info else {}
            current_group = str(first_node.get("node_id", ""))
            audit_groups_str = ",".join(str(n["node_id"]) for n in groups_info)
        else:
            # 向后兼容：旧格式 "group_id1,group_id2"
            auth_groups = self.workflow.audit_auth_groups or ""
            raw_groups = [g.strip() for g in auth_groups.split(",") if g.strip()]
            groups_info = [
                {
                    "order": i + 1,
                    "node_id": None,
                    "node_name": f"第 {i + 1} 级审批",
                    "approver_type": "any_reviewer",  # 旧格式不限制审批人
                    "approver_ids": [],
                    "status": AuditStatus.PENDING,
                    "operator": None,
                    "operated_at": None,
                }
                for i, _ in enumerate(raw_groups)
            ] or [
                {
                    "order": 1,
                    "node_id": None,
                    "node_name": "审批",
                    "approver_type": "any_reviewer",
                    "approver_ids": [],
                    "status": AuditStatus.PENDING,
                    "operator": None,
                    "operated_at": None,
                }
            ]
            current_group = raw_groups[0] if raw_groups else ""
            audit_groups_str = auth_groups

        audit = WorkflowAudit(
            workflow_id=self.workflow.id,
            workflow_type=int(self.workflow_type),
            workflow_title=self.workflow.workflow_name,
            current_audit_auth_group=current_group,
            current_status=AuditStatus.PENDING,
            audit_auth_groups=audit_groups_str,
            audit_auth_groups_info=json.dumps(groups_info, ensure_ascii=False),
            create_user=operator.get("username", ""),
            create_user_id=operator.get("id", 0),
        )
        db.add(audit)
        await db.flush()

        await self._write_log(
            db, audit.id, operator, OP_SUBMIT, remark=f"提交工单：{self.workflow.workflow_name}"
        )
        await db.commit()

        logger.info("audit_created: workflow=%s nodes=%d", self.workflow.id, len(groups_info))
        return audit

    # ── 审批操作 ──────────────────────────────────────────────

    @staticmethod
    async def operate(
        db: AsyncSession,
        workflow_id: int,
        action: str,
        operator: dict,
        remark: str = "",
    ) -> dict:
        wf_result = await db.execute(select(SqlWorkflow).where(SqlWorkflow.id == workflow_id))
        workflow = wf_result.scalar_one_or_none()
        if not workflow:
            raise NotFoundException(f"工单 ID={workflow_id} 不存在")

        audit_result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == workflow_id)
        )
        audit = audit_result.scalar_one_or_none()
        if not audit:
            raise AppException("审批记录不存在", code=400)

        if action == OP_PASS:
            return await AuditService._do_pass(db, workflow, audit, operator, remark)
        elif action == OP_REJECT:
            return await AuditService._do_reject(db, workflow, audit, operator, remark)
        elif action == OP_CANCEL:
            return await AuditService._do_cancel(db, workflow, audit, operator, remark)
        else:
            raise AppException(f"不支持的操作：{action}", code=400)

    @staticmethod
    async def _do_pass(
        db: AsyncSession,
        workflow: SqlWorkflow,
        audit: WorkflowAudit,
        operator: dict,
        remark: str,
    ) -> dict:
        if workflow.status not in (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.REVIEW_PASS):
            raise AppException("当前状态不允许审批通过", code=400)

        groups_info = json.loads(audit.audit_auth_groups_info or "[]")
        current_node = next(
            (g for g in groups_info if g.get("status") == AuditStatus.PENDING),
            None,
        )
        if current_node is None:
            raise AppException("审批链已完成，无法重复审批", code=400)

        # 校验审批人权限
        await AuditService._check_approver_permission(db, operator, current_node)

        # 标记当前节点已通过
        current_node["status"] = AuditStatus.PASSED
        current_node["operator"] = operator.get("username")
        current_node["operated_at"] = datetime.now(UTC).isoformat()

        next_pending = next(
            (g for g in groups_info if g.get("status") == AuditStatus.PENDING),
            None,
        )

        audit.audit_auth_groups_info = json.dumps(groups_info, ensure_ascii=False)

        if next_pending:
            audit.current_audit_auth_group = str(next_pending.get("node_id", ""))
            audit.current_status = AuditStatus.PENDING
            workflow.status = WorkflowStatus.PENDING_REVIEW
            msg = (
                f"第 {current_node['order']} 级「{current_node.get('node_name', '')}」审批通过，"
                f"等待下一级「{next_pending.get('node_name', '')}」审批"
            )
        else:
            audit.current_status = AuditStatus.PASSED
            workflow.status = WorkflowStatus.REVIEW_PASS
            msg = "全部审批通过，工单已就绪"

        await AuditService._write_log(db, audit.id, operator, OP_PASS, remark=remark or msg)
        await db.commit()
        return {"msg": msg, "status": workflow.status}

    @staticmethod
    async def _do_reject(
        db: AsyncSession,
        workflow: SqlWorkflow,
        audit: WorkflowAudit,
        operator: dict,
        remark: str,
    ) -> dict:
        if workflow.status not in (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.REVIEW_PASS):
            raise AppException("当前状态不允许驳回", code=400)

        groups_info = json.loads(audit.audit_auth_groups_info or "[]")
        current_node = next(
            (g for g in groups_info if g.get("status") == AuditStatus.PENDING),
            None,
        )

        # 校验审批人权限（current_node 为 None 说明链已完成，仍可驳回，跳过节点校验）
        if current_node is not None:
            await AuditService._check_approver_permission(db, operator, current_node)

        audit.current_status = AuditStatus.REJECTED
        workflow.status = WorkflowStatus.AUTO_REVIEW_FAIL

        node_desc = f"「{current_node['node_name']}」" if current_node else ""
        await AuditService._write_log(
            db, audit.id, operator, OP_REJECT, remark=remark or f"{node_desc}审批人驳回"
        )
        await db.commit()
        return {"msg": "工单已驳回", "status": workflow.status}

    @staticmethod
    async def _do_cancel(
        db: AsyncSession,
        workflow: SqlWorkflow,
        audit: WorkflowAudit,
        operator: dict,
        remark: str,
    ) -> dict:
        cancelable = (
            WorkflowStatus.PENDING_REVIEW,
            WorkflowStatus.AUTO_REVIEW_FAIL,
            WorkflowStatus.REVIEW_PASS,
            WorkflowStatus.TIMING_TASK,
        )
        if workflow.status not in cancelable:
            raise AppException("当前状态不允许取消", code=400)

        # 取消只允许：工单提交人 或 超管
        if not operator.get("is_superuser") and operator.get("username") != workflow.engineer:
            raise AppException("只有工单提交人或超管可以取消工单", code=403)

        audit.current_status = AuditStatus.CANCELED
        workflow.status = WorkflowStatus.ABORT

        await AuditService._write_log(
            db, audit.id, operator, OP_CANCEL, remark=remark or "提交人/超管取消工单"
        )
        await db.commit()
        return {"msg": "工单已取消", "status": workflow.status}

    # ── 审批人权限校验 ────────────────────────────────────────

    @staticmethod
    async def _check_approver_permission(
        db: AsyncSession,
        operator: dict,
        node: dict,
    ) -> None:
        """
        校验 operator 是否有权限审批 node。
        超级管理员绕过所有节点限制。
        """
        if operator.get("is_superuser"):
            return

        approver_type = node.get("approver_type", "any_reviewer")
        approver_ids: list[int] = node.get("approver_ids", [])

        if approver_type == "any_reviewer":
            # 任何拥有 sql_review 权限的用户
            if "sql_review" not in operator.get("permissions", []):
                raise AppException(
                    f"您没有审批权限（节点「{node.get('node_name', '')}」要求 sql_review 权限）",
                    code=403,
                )

        elif approver_type == "users":
            # 指定用户列表
            if operator.get("id") not in approver_ids:
                raise AppException(
                    f"您不在节点「{node.get('node_name', '')}」的审批人列表中",
                    code=403,
                )

        elif approver_type == "group":
            # 资源组成员（含用户组 → 资源组链路）
            from app.models.role import UserGroup
            from app.models.user import Users

            user_result = await db.execute(
                select(Users)
                .options(
                    selectinload(Users.user_groups).selectinload(UserGroup.resource_groups),
                )
                .where(Users.id == operator.get("id"))
            )
            user_obj = user_result.scalar_one_or_none()
            group_rg_ids: set[int] = set()
            if user_obj:
                for ug in user_obj.user_groups:
                    for rg in ug.resource_groups:
                        group_rg_ids.add(rg.id)
            if not any(gid in approver_ids for gid in group_rg_ids):
                raise AppException(
                    f"您不在节点「{node.get('node_name', '')}」要求的资源组中",
                    code=403,
                )

        elif approver_type == "manager":
            # 直属上级审批
            applicant_id = node.get("applicant_id")
            if applicant_id:
                from app.models.user import Users as UserModel

                applicant = await db.execute(select(UserModel).where(UserModel.id == applicant_id))
                applicant_obj = applicant.scalar_one_or_none()
                if not applicant_obj or applicant_obj.manager_id != operator.get("id"):
                    raise AppException(
                        f"您不是申请人「{node.get('applicant_name', '')}」的直属上级",
                        code=403,
                    )
            else:
                raise AppException("无法确认申请人，无法验证直属上级审批权限", code=403)

        elif approver_type == "user_group":
            # 用户组成员审批
            approver_group_id = node.get("approver_group_id")
            if approver_group_id:
                from app.models.role import user_group_member

                result = await db.execute(
                    select(user_group_member)
                    .where(user_group_member.c.group_id == approver_group_id)
                    .where(user_group_member.c.user_id == operator.get("id"))
                )
                if not result.first():
                    raise AppException(
                        f"您不在节点「{node.get('node_name', '')}」要求的用户组中",
                        code=403,
                    )
            else:
                raise AppException("审批节点未指定用户组", code=403)

        elif approver_type == "role":
            # 角色持有者审批
            approver_role_id = node.get("approver_role_id")
            if approver_role_id:
                if operator.get("role_id") != approver_role_id:
                    raise AppException(
                        f"您没有节点「{node.get('node_name', '')}」要求的角色",
                        code=403,
                    )
            else:
                raise AppException("审批节点未指定角色", code=403)

        else:
            raise AppException(
                f"审批节点类型「{approver_type}」不在当前 v2-lite 首发范围内，请调整审批流模板",
                code=400,
            )

    # ── 待审批工单（按节点权限过滤）────────────────────────────

    @staticmethod
    async def get_pending_workflow_ids_for_user(
        db: AsyncSession,
        user: dict,
    ) -> set[int]:
        """
        返回当前用户有权限审批的待审批工单 ID 集合。
        供工单列表把“我提交的工单”和“待我审批的工单”并集展示使用。
        """
        from app.models.instance import Instance

        stmt = (
            select(SqlWorkflow, WorkflowAudit, Instance.instance_name)
            .join(WorkflowAudit, WorkflowAudit.workflow_id == SqlWorkflow.id)
            .outerjoin(Instance, SqlWorkflow.instance_id == Instance.id)
            .where(SqlWorkflow.status == WorkflowStatus.PENDING_REVIEW)
            .order_by(SqlWorkflow.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        authorized_ids: set[int] = set()
        for workflow, audit, _inst_name in rows:
            groups_info = json.loads(audit.audit_auth_groups_info or "[]")
            current_node = next(
                (g for g in groups_info if g.get("status") == AuditStatus.PENDING),
                None,
            )
            if current_node is None:
                continue

            try:
                await AuditService._check_approver_permission(db, user, current_node)
                authorized_ids.add(workflow.id)
            except AppException:
                continue

        return authorized_ids

    @staticmethod
    async def get_audited_workflow_ids_for_user(
        db: AsyncSession,
        user: dict,
    ) -> set[int]:
        """
        返回当前用户已经审批过的工单 ID 集合。
        仅统计真正的审批动作（pass / reject），不包含 submit/cancel/execute。
        """
        audit_rows = await db.execute(
            select(WorkflowAudit.workflow_id)
            .join(WorkflowLog, WorkflowLog.audit_id == WorkflowAudit.id)
            .where(WorkflowLog.operator_id == user.get("id"))
            .where(WorkflowLog.operation_type.in_((OP_PASS, OP_REJECT)))
        )
        return set(audit_rows.scalars().all())

    @staticmethod
    async def get_pending_for_user(
        db: AsyncSession,
        user: dict,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict]]:
        """
        返回当前用户有权限审批的待审批工单列表。
        超管可看全部，普通用户按节点权限过滤。
        """
        from app.models.instance import Instance
        from app.services.workflow import WorkflowService  # noqa: PLC0415

        # 获取所有 PENDING_REVIEW 工单及其 audit 记录
        stmt = (
            select(SqlWorkflow, WorkflowAudit, Instance.instance_name)
            .join(WorkflowAudit, WorkflowAudit.workflow_id == SqlWorkflow.id)
            .outerjoin(Instance, SqlWorkflow.instance_id == Instance.id)
            .where(SqlWorkflow.status == WorkflowStatus.PENDING_REVIEW)
            .order_by(SqlWorkflow.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        authorized_ids = await AuditService.get_pending_workflow_ids_for_user(db, user)
        authorized = []
        for workflow, audit, inst_name in rows:
            if workflow.id not in authorized_ids:
                continue
            groups_info = json.loads(audit.audit_auth_groups_info or "[]")
            current_node = next(
                (g for g in groups_info if g.get("status") == AuditStatus.PENDING),
                None,
            )
            if current_node is None:
                continue
            authorized.append((workflow, inst_name, current_node))

        total = len(authorized)
        paginated = authorized[(page - 1) * page_size : page * page_size]

        items = []
        for workflow, inst_name, current_node in paginated:
            item = WorkflowService._fmt_workflow(workflow, inst_name or "")
            item["current_node"] = {
                "order": current_node.get("order"),
                "node_name": current_node.get("node_name"),
                "approver_type": current_node.get("approver_type"),
            }
            items.append(item)

        return total, items

    # ── 审批日志 ──────────────────────────────────────────────

    @staticmethod
    async def get_audit_logs(db: AsyncSession, workflow_id: int) -> list[dict]:
        from app.models.user import Users

        result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == workflow_id)
        )
        audit = result.scalar_one_or_none()
        if not audit:
            return []

        logs_result = await db.execute(
            select(WorkflowLog)
            .where(WorkflowLog.audit_id == audit.id)
            .order_by(WorkflowLog.created_at)
        )
        logs = logs_result.scalars().all()
        operator_ids = [log.operator_id for log in logs if log.operator_id]
        user_map: dict[int, Users] = {}
        if operator_ids:
            users_result = await db.execute(select(Users).where(Users.id.in_(operator_ids)))
            user_map = {user.id: user for user in users_result.scalars().all()}

        return [
            {
                "operator": (
                    user_map[log.operator_id].display_name
                    if log.operator_id in user_map and user_map[log.operator_id].display_name
                    else log.operator
                ),
                "operation_type": log.operation_type,
                "remark": log.remark,
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
            for log in logs
        ]

    @staticmethod
    async def get_audit_info(db: AsyncSession, workflow_id: int) -> dict | None:
        result = await db.execute(
            select(WorkflowAudit).where(WorkflowAudit.workflow_id == workflow_id)
        )
        audit = result.scalar_one_or_none()
        if not audit:
            return None
        groups_info = json.loads(audit.audit_auth_groups_info or "[]")
        return {
            "current_audit_auth_group": audit.current_audit_auth_group,
            "current_status": audit.current_status,
            "nodes": [
                {
                    "order": n.get("order"),
                    "node_name": n.get("node_name"),
                    "approver_type": n.get("approver_type"),
                    "approver_ids": n.get("approver_ids"),
                    "approver_group_id": n.get("approver_group_id"),
                    "approver_role_id": n.get("approver_role_id"),
                    "applicant_id": n.get("applicant_id"),
                    "applicant_name": n.get("applicant_name"),
                    "status": n.get("status"),
                    "operator": n.get("operator"),
                    "operated_at": n.get("operated_at"),
                }
                for n in groups_info
            ],
        }

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    async def _write_log(
        db: AsyncSession,
        audit_id: int,
        operator: dict,
        operation_type: str,
        remark: str = "",
    ) -> None:
        log = WorkflowLog(
            audit_id=audit_id,
            operator=operator.get("username", "system"),
            operator_id=operator.get("id", 0),
            operation_type=operation_type,
            remark=remark,
        )
        db.add(log)
