"""`ApprovalFlowService` 单测（此前整体约 22% 覆盖）。

以 AsyncMock 隔离 DB，覆盖列表/详情/创建/更新/停用/工单快照，含
节点全量替换、停用与空节点校验、NotFound 分支及 _fmt_* 序列化。
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.services.approval_flow import ApprovalFlowService


def _node(nid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=nid, order=1, node_name="DBA初审", approver_type="users",
        approver_ids=json.dumps([3, 7]), approver_group_id=None, approver_role_id=None,
    )


def _flow(active: bool = True, nodes: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=5, name="流程A", description="desc", is_active=active,
        nodes=nodes if nodes is not None else [_node()],
        created_by="admin", created_at=None,
    )


def _scalars_all(rows) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _one(obj) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


# ── list_flows / get_flow (含 _fmt_*) ───────────────────────

@pytest.mark.asyncio
async def test_list_flows_serializes_nodes():
    db = _make_db()
    db.execute.return_value = _scalars_all([_flow()])
    out = await ApprovalFlowService.list_flows(db)
    assert len(out) == 1
    assert out[0]["node_count"] == 1
    assert out[0]["nodes"][0]["approver_ids"] == [3, 7]


@pytest.mark.asyncio
async def test_list_flows_include_inactive_branch():
    db = _make_db()
    db.execute.return_value = _scalars_all([])
    assert await ApprovalFlowService.list_flows(db, include_inactive=True) == []


@pytest.mark.asyncio
async def test_get_flow_found_and_optional_fields():
    node = _node()
    node.approver_group_id = 3
    node.approver_role_id = 9
    db = _make_db()
    db.execute.return_value = _one(_flow(nodes=[node]))
    out = await ApprovalFlowService.get_flow(db, 5)
    assert out["nodes"][0]["approver_group_id"] == 3
    assert out["nodes"][0]["approver_role_id"] == 9


@pytest.mark.asyncio
async def test_get_flow_missing_raises():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await ApprovalFlowService.get_flow(db, 404)


# ── create_flow ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_flow_persists_and_reloads():
    node_data = SimpleNamespace(
        order=1, node_name="n1", approver_type="users",
        approver_ids=[1, 2], approver_group_id=None, approver_role_id=None,
    )
    data = SimpleNamespace(name="F", description="d", nodes=[node_data])
    db = _make_db()
    # create_flow 末尾 get_flow 重新加载
    db.execute.return_value = _one(_flow())

    out = await ApprovalFlowService.create_flow(db, data, {"username": "admin", "id": 1})

    assert out["name"] == "流程A"
    db.flush.assert_awaited()
    db.commit.assert_awaited_once()
    # 1 个 flow + 1 个 node 均被 add
    assert db.add.call_count == 2


# ── update_flow ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_flow_metadata_only():
    flow = _flow()
    db = _make_db()
    db.execute.side_effect = [_one(flow), _one(flow)]  # 加载 + 末尾 get_flow
    data = SimpleNamespace(name="新名", description="新描述", is_active=False, nodes=None)

    await ApprovalFlowService.update_flow(db, 5, data)

    assert flow.name == "新名"
    assert flow.description == "新描述"
    assert flow.is_active is False
    db.delete.assert_not_called()


@pytest.mark.asyncio
async def test_update_flow_replaces_nodes():
    flow = _flow(nodes=[_node(1), _node(2)])
    node_data = SimpleNamespace(
        order=1, node_name="new", approver_type="users",
        approver_ids=[9], approver_group_id=None, approver_role_id=None,
    )
    db = _make_db()
    db.execute.side_effect = [_one(flow), _one(_flow())]
    data = SimpleNamespace(name=None, description=None, is_active=None, nodes=[node_data])

    await ApprovalFlowService.update_flow(db, 5, data)

    # 旧 2 节点删除，新增 1 节点
    assert db.delete.await_count == 2
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_update_flow_missing_raises():
    db = _make_db()
    db.execute.return_value = _one(None)
    data = SimpleNamespace(name="x", description=None, is_active=None, nodes=None)
    with pytest.raises(NotFoundException):
        await ApprovalFlowService.update_flow(db, 404, data)


# ── deactivate_flow ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_flow_sets_inactive():
    flow = _flow()
    db = _make_db()
    db.execute.return_value = _one(flow)
    await ApprovalFlowService.deactivate_flow(db, 5)
    assert flow.is_active is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivate_flow_missing_raises():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await ApprovalFlowService.deactivate_flow(db, 404)


# ── snapshot_for_workflow ───────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_returns_pending_nodes():
    db = _make_db()
    db.execute.return_value = _one(_flow())
    snap = await ApprovalFlowService.snapshot_for_workflow(db, 5)
    assert snap[0]["status"] == 0
    assert snap[0]["operator"] is None
    assert snap[0]["approver_ids"] == [3, 7]


@pytest.mark.asyncio
async def test_snapshot_inactive_flow_raises():
    db = _make_db()
    db.execute.return_value = _one(_flow(active=False))
    with pytest.raises(AppException):
        await ApprovalFlowService.snapshot_for_workflow(db, 5)


@pytest.mark.asyncio
async def test_snapshot_no_nodes_raises():
    db = _make_db()
    db.execute.return_value = _one(_flow(nodes=[]))
    with pytest.raises(AppException):
        await ApprovalFlowService.snapshot_for_workflow(db, 5)


@pytest.mark.asyncio
async def test_snapshot_missing_flow_raises():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await ApprovalFlowService.snapshot_for_workflow(db, 404)
