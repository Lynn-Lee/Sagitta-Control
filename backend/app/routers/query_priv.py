"""
查询权限管理路由（Sprint 2）。
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user
from app.models.instance import Instance
from app.models.user import Users
from app.schemas.query import AuditPrivRequest, PrivApplyRequest, RevokePrivilegeRequest
from app.services.audit_log import AuditLogService
from app.services.query_priv import QueryPrivService

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_name_maps(db: AsyncSession, applies: list) -> tuple[dict[int, str], dict[int, dict]]:
    instance_ids = sorted({a.instance_id for a in applies if a.instance_id})
    user_ids = sorted({a.user_id for a in applies if a.user_id})

    instance_name_map: dict[int, str] = {}
    user_map: dict[int, dict] = {}

    if instance_ids:
        result = await db.execute(
            select(Instance.id, Instance.instance_name).where(Instance.id.in_(instance_ids))
        )
        instance_name_map = {row.id: row.instance_name for row in result.all()}

    if user_ids:
        result = await db.execute(
            select(Users.id, Users.username, Users.display_name).where(Users.id.in_(user_ids))
        )
        user_map = {
            row.id: {
                "username": row.username,
                "display_name": row.display_name,
            }
            for row in result.all()
        }

    return instance_name_map, user_map


def _build_approval_progress(apply, user_map: dict[int, dict]) -> str | None:
    applicant = user_map.get(apply.user_id or 0, {})
    applicant_name = applicant.get("display_name") or applicant.get("username")
    if not apply.audit_auth_groups_info:
        return applicant_name or None

    nodes = QueryPrivService._safe_load_nodes(apply.audit_auth_groups_info)
    parts: list[str] = []
    if applicant_name:
        parts.append(applicant_name)
    for node in nodes:
        operator = node.get("operator_display") or node.get("operator")
        if operator:
            parts.append(str(operator))
        elif node.get("status") == 0:
            parts.append(f"{node.get('node_name', '待审批')}（待审批）")
    return " -> ".join(parts) if parts else None


def _extract_latest_action(apply, username: str) -> tuple[str | None, str | None, str | None]:
    if not apply.audit_auth_groups_info:
        return None, None, None
    nodes = QueryPrivService._safe_load_nodes(apply.audit_auth_groups_info)
    acted_nodes = [node for node in nodes if node.get("operator") == username]
    if not acted_nodes:
        return None, None, None
    latest_node = acted_nodes[-1]
    action = "通过" if latest_node.get("status") == 1 else "驳回" if latest_node.get("status") == 2 else "—"
    return latest_node.get("node_name"), action, latest_node.get("operated_at")


def _serialize_apply_items(
    applies: list,
    *,
    can_audit_ids: set[int],
    instance_name_map: dict[int, str],
    user_map: dict[int, dict],
    operator_username: str,
) -> list[dict]:
    items: list[dict] = []
    for apply in applies:
        applicant = user_map.get(apply.user_id or 0, {})
        acted_node_name, acted_action, acted_at = _extract_latest_action(apply, operator_username)
        items.append(
            {
                "id": apply.id,
                "title": apply.title,
                "instance_id": apply.instance_id,
                "instance_name": instance_name_map.get(apply.instance_id, f"实例#{apply.instance_id}"),
                "flow_id": apply.flow_id,
                "applicant_name": applicant.get("display_name") or applicant.get("username"),
                "applicant_username": applicant.get("username"),
                "db_name": apply.db_name,
                "table_name": apply.table_name,
                "scope_type": apply.scope_type,
                "valid_date": apply.valid_date.isoformat(),
                "limit_num": apply.limit_num,
                "priv_type": apply.priv_type,
                "apply_reason": apply.apply_reason,
                "status": apply.status,
                "current_node_name": (
                    QueryPrivService._get_current_pending_node(apply) or {}
                ).get("node_name") if apply.status == 0 and apply.audit_auth_groups_info else None,
                "approval_progress": _build_approval_progress(apply, user_map),
                "acted_node_name": acted_node_name,
                "acted_action": acted_action,
                "acted_at": acted_at,
                "can_audit": apply.id in can_audit_ids,
                "created_at": apply.created_at.isoformat() if apply.created_at else "",
            }
        )
    return items


@router.get("/privileges/", summary="我的查询权限列表")
async def list_my_privileges(
    instance_id: int | None = None,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    privs = await QueryPrivService.list_my_privileges(
        db, user_id=user["id"], instance_id=instance_id
    )
    return {
        "items": [
            {
                "id": p.id,
                "instance_id": p.instance_id,
                "instance_name": None,
                "db_name": p.db_name,
                "table_name": p.table_name,
                "scope_type": p.scope_type,
                "valid_date": p.valid_date.isoformat(),
                "limit_num": p.limit_num,
                "priv_type": p.priv_type,
                "created_at": p.created_at.isoformat() if p.created_at else "",
            }
            for p in privs
        ]
    }


@router.post("/privileges/apply/", summary="申请查询权限")
async def apply_privilege(
    data: PrivApplyRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    apply = await QueryPrivService.apply_privilege(
        db=db,
        user_id=user["id"],
        instance_id=data.instance_id,
        group_id=data.group_id,
        flow_id=data.flow_id,
        db_name=data.db_name,
        table_name=data.table_name,
        valid_date=data.valid_date,
        limit_num=data.limit_num,
        priv_type=data.priv_type,
        apply_reason=data.apply_reason,
        audit_auth_groups=data.audit_auth_groups,
        title=data.title,
        scope_type=data.scope_type,
        user=user,
    )
    return {"status": 0, "msg": "申请已提交", "data": {"apply_id": apply.id}}


@router.get("/privileges/applies/", summary="权限申请列表")
async def list_applies(
    status: int | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, applies = await QueryPrivService.list_applies(
        db, user_id=user["id"], auditor=None, status=status, page=page, page_size=page_size
    )
    instance_name_map, user_map = await _load_name_maps(db, applies)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": _serialize_apply_items(
            applies,
            can_audit_ids=set(),
            instance_name_map=instance_name_map,
            user_map=user_map,
            operator_username=user.get("username", ""),
        ),
    }


@router.get("/privileges/audit-records/", summary="查询权限审批记录")
async def list_audit_records(
    status: int | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, applies, can_audit_ids = await QueryPrivService.list_audit_records(
        db=db,
        auditor=user,
        status=status,
        page=page,
        page_size=page_size,
    )
    instance_name_map, user_map = await _load_name_maps(db, applies)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": _serialize_apply_items(
            applies,
            can_audit_ids=can_audit_ids,
            instance_name_map=instance_name_map,
            user_map=user_map,
            operator_username=user.get("username", ""),
        ),
    }


@router.post(
    "/privileges/audit/",
    summary="审批查询权限申请",
)
async def audit_apply(
    apply_id: int,
    data: AuditPrivRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    apply = await QueryPrivService.audit_apply(
        db=db,
        apply_id=apply_id,
        auditor=user,
        action=data.action,
        remark=data.remark,
        valid_date_override=data.valid_date,
    )
    if data.action == "pass":
        msg = "审批通过"
        if apply.status == 0:
            current_node = QueryPrivService._get_current_pending_node(apply)
            if current_node:
                msg = f"已流转到下一审批节点：{current_node.get('node_name', '')}"
    else:
        msg = "已驳回"
    return {"status": 0, "msg": msg, "data": {"apply_id": apply.id, "status": apply.status}}


@router.get("/privileges/manage/", summary="查询权限统一视角")
async def list_manage_privileges(
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    instance_id: int | None = None,
    user_id: int | None = None,
    db_name: str | None = None,
    status: str = QParam("active", pattern="^(active|revoked)$"),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    scope, total, items = await QueryPrivService.list_manage_privileges(
        db=db,
        user=user,
        page=page,
        page_size=page_size,
        instance_id=instance_id,
        user_id=user_id,
        db_name=db_name,
        status=status,
    )
    return {
        "scope": scope,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.delete(
    "/privileges/{priv_id}/",
    summary="撤销查询权限",
)
async def revoke_privilege(
    priv_id: int,
    request: Request,
    data: RevokePrivilegeRequest | None = None,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    priv = await QueryPrivService.revoke_privilege(
        db,
        priv_id=priv_id,
        operator=user,
        reason=data.reason if data else "",
    )
    await AuditLogService.write(
        db,
        user,
        action="revoke_query_privilege",
        module="query",
        detail=(
            f"撤销查询权限 #{priv.id}，用户ID={priv.user_id}，实例ID={priv.instance_id}，"
            f"库={priv.db_name}，表={priv.table_name or '全库'}"
        ),
        request=request,
        remark=data.reason if data else "",
    )
    return {"status": 0, "msg": "权限已撤销"}
