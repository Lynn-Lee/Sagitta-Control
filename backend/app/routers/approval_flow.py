"""
审批流模板管理路由。
仅超级管理员可创建/修改/停用，所有有 sql_review 权限的用户可查看列表。
"""
from typing import Any
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_superuser, current_user
from app.schemas.approval_flow import ApprovalFlowCreate, ApprovalFlowUpdate
from app.services.approval_flow import ApprovalFlowService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="审批流列表")
async def list_flows(
    include_inactive: bool = False,
    user: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """返回所有审批流模板。默认只返回启用状态，超管可加 include_inactive=true 查看全部。"""
    if include_inactive and not user.get("is_superuser"):
        include_inactive = False
    flows = await ApprovalFlowService.list_flows(db, include_inactive=include_inactive)
    return {"total": len(flows), "items": flows}


@router.post("/", summary="创建审批流", dependencies=[Depends(current_superuser)])
async def create_flow(
    data: ApprovalFlowCreate,
    user: dict[str, Any] = Depends(current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    flow = await ApprovalFlowService.create_flow(db, data, operator=user)
    logger.info("approval_flow_created: id=%s name=%s by=%s", flow["id"], flow["name"], user.get("username"))
    return {"status": 0, "msg": "审批流创建成功", "data": flow}


@router.get("/{flow_id}/", summary="审批流详情")
async def get_flow(
    flow_id: int,
    _: dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    flow = await ApprovalFlowService.get_flow(db, flow_id)
    return {"status": 0, "data": flow}


@router.put("/{flow_id}/", summary="更新审批流", dependencies=[Depends(current_superuser)])
async def update_flow(
    flow_id: int,
    data: ApprovalFlowUpdate,
    user: dict[str, Any] = Depends(current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    flow = await ApprovalFlowService.update_flow(db, flow_id, data)
    logger.info("approval_flow_updated: id=%s by=%s", flow_id, user.get("username"))
    return {"status": 0, "msg": "审批流已更新", "data": flow}


@router.delete("/{flow_id}/", summary="停用审批流（软删除）", dependencies=[Depends(current_superuser)])
async def deactivate_flow(
    flow_id: int,
    user: dict[str, Any] = Depends(current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ApprovalFlowService.deactivate_flow(db, flow_id)
    logger.info("approval_flow_deactivated: id=%s by=%s", flow_id, user.get("username"))
    return {"status": 0, "msg": "审批流已停用"}
