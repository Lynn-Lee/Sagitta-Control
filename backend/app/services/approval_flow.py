"""
审批流模板服务。
负责流程模板的 CRUD 以及为工单创建时生成节点快照。
"""

from __future__ import annotations

from typing import Any

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.models.approval_flow import ApprovalFlow, ApprovalFlowNode
from app.schemas.approval_flow import ApprovalFlowCreate, ApprovalFlowUpdate

logger = logging.getLogger(__name__)


def _fmt_node(node: ApprovalFlowNode) -> dict[str, Any]:
    result = {
        "id": node.id,
        "order": node.order,
        "node_name": node.node_name,
        "approver_type": node.approver_type,
        "approver_ids": json.loads(node.approver_ids or "[]"),
    }
    if node.approver_group_id:
        result["approver_group_id"] = node.approver_group_id
    if node.approver_role_id:
        result["approver_role_id"] = node.approver_role_id
    return result


def _fmt_flow(flow: ApprovalFlow) -> dict[str, Any]:
    return {
        "id": flow.id,
        "name": flow.name,
        "description": flow.description,
        "is_active": flow.is_active,
        "node_count": len(flow.nodes),
        "nodes": [_fmt_node(n) for n in flow.nodes],
        "created_by": flow.created_by,
        "created_at": flow.created_at.isoformat() if flow.created_at else "",
    }


class ApprovalFlowService:
    @staticmethod
    async def list_flows(db: AsyncSession, include_inactive: bool = False) -> list[dict[str, Any]]:
        """列出所有审批流模板（默认只返回启用的）。"""
        stmt = select(ApprovalFlow).options(selectinload(ApprovalFlow.nodes))
        if not include_inactive:
            stmt = stmt.where(ApprovalFlow.is_active.is_(True))
        stmt = stmt.order_by(ApprovalFlow.id)
        result = await db.execute(stmt)
        return [_fmt_flow(f) for f in result.scalars().all()]

    @staticmethod
    async def get_flow(db: AsyncSession, flow_id: int) -> dict[str, Any]:
        """获取单个流程模板详情。"""
        result = await db.execute(
            select(ApprovalFlow)
            .options(selectinload(ApprovalFlow.nodes))
            .where(ApprovalFlow.id == flow_id)
        )
        flow = result.scalar_one_or_none()
        if not flow:
            raise NotFoundException(f"审批流 ID={flow_id} 不存在")
        return _fmt_flow(flow)

    @staticmethod
    async def create_flow(
        db: AsyncSession,
        data: ApprovalFlowCreate,
        operator: dict[str, Any],
    ) -> dict[str, Any]:
        """创建审批流模板（含节点）。"""
        flow = ApprovalFlow(
            name=data.name,
            description=data.description,
            is_active=True,
            created_by=operator.get("username", ""),
            created_by_id=operator.get("id"),
        )
        db.add(flow)
        await db.flush()  # 获取 flow.id

        for node_data in data.nodes:
            node = ApprovalFlowNode(
                flow_id=flow.id,
                order=node_data.order,
                node_name=node_data.node_name,
                approver_type=node_data.approver_type,
                approver_ids=json.dumps(node_data.approver_ids),
                approver_group_id=node_data.approver_group_id,
                approver_role_id=node_data.approver_role_id,
            )
            db.add(node)

        await db.commit()
        await db.refresh(flow)

        # 重新加载含节点的完整对象
        return await ApprovalFlowService.get_flow(db, flow.id)

    @staticmethod
    async def update_flow(
        db: AsyncSession,
        flow_id: int,
        data: ApprovalFlowUpdate,
    ) -> dict[str, Any]:
        """
        更新审批流模板。
        如果传入 nodes，则全量替换节点（删除旧节点，重建新节点）。
        不传 nodes 则只更新元数据。
        """
        result = await db.execute(
            select(ApprovalFlow)
            .options(selectinload(ApprovalFlow.nodes))
            .where(ApprovalFlow.id == flow_id)
        )
        flow = result.scalar_one_or_none()
        if not flow:
            raise NotFoundException(f"审批流 ID={flow_id} 不存在")

        if data.name is not None:
            flow.name = data.name
        if data.description is not None:
            flow.description = data.description
        if data.is_active is not None:
            flow.is_active = data.is_active

        if data.nodes is not None:
            # 全量替换节点：删旧建新
            for old_node in list(flow.nodes):
                await db.delete(old_node)
            await db.flush()

            for node_data in data.nodes:
                node = ApprovalFlowNode(
                    flow_id=flow.id,
                    order=node_data.order,
                    node_name=node_data.node_name,
                    approver_type=node_data.approver_type,
                    approver_ids=json.dumps(node_data.approver_ids),
                    approver_group_id=node_data.approver_group_id,
                    approver_role_id=node_data.approver_role_id,
                )
                db.add(node)

        await db.commit()
        return await ApprovalFlowService.get_flow(db, flow_id)

    @staticmethod
    async def deactivate_flow(db: AsyncSession, flow_id: int) -> None:
        """软删除：停用审批流（不物理删除，避免影响历史工单记录）。"""
        result = await db.execute(select(ApprovalFlow).where(ApprovalFlow.id == flow_id))
        flow = result.scalar_one_or_none()
        if not flow:
            raise NotFoundException(f"审批流 ID={flow_id} 不存在")
        flow.is_active = False
        await db.commit()

    @staticmethod
    async def snapshot_for_workflow(db: AsyncSession, flow_id: int) -> list[dict[str, Any]]:
        """
        为工单创建时生成节点快照列表。
        快照结构与 audit_auth_groups_info 的节点格式一致：
        [
            {
                "order": 1,
                "node_id": 1,
                "node_name": "DBA初审",
                "approver_type": "users",
                "approver_ids": [3, 7],
                "status": 0,          # AuditStatus.PENDING
                "operator": null,
                "operated_at": null
            },
            ...
        ]
        """
        result = await db.execute(
            select(ApprovalFlow)
            .options(selectinload(ApprovalFlow.nodes))
            .where(ApprovalFlow.id == flow_id)
        )
        flow = result.scalar_one_or_none()
        if not flow:
            raise NotFoundException(f"审批流 ID={flow_id} 不存在")
        if not flow.is_active:
            raise AppException(f"审批流「{flow.name}」已停用，请选择其他流程", code=400)
        if not flow.nodes:
            raise AppException(f"审批流「{flow.name}」没有配置审批节点", code=400)

        return [
            {
                "order": node.order,
                "node_id": node.id,
                "node_name": node.node_name,
                "approver_type": node.approver_type,
                "approver_ids": json.loads(node.approver_ids or "[]"),
                "approver_group_id": node.approver_group_id,
                "approver_role_id": node.approver_role_id,
                "status": 0,  # AuditStatus.PENDING
                "operator": None,
                "operated_at": None,
            }
            for node in flow.nodes  # 已按 order 排序（relationship 定义了 order_by）
        ]
