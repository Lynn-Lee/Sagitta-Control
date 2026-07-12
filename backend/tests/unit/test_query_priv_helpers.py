"""`QueryPrivService` 纯逻辑与权限判定辅助方法单测。

该服务此前整体覆盖偏低（约 41%）。这里聚焦无需真实 DB 的纯函数与
以 AsyncMock 隔离的三级授权探测（instance/database/table），锁定：
访问范围判定、绕过授权判定、scope 归一化、pg 表名候选、快照装饰等分支。
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.workflow import AuditStatus
from app.services.query_priv import QueryPrivService


def _instance(db_type: str = "mysql", rg_ids: list[int] | None = None) -> SimpleNamespace:
    rgs = [SimpleNamespace(id=i) for i in (rg_ids or [])]
    return SimpleNamespace(db_type=db_type, resource_groups=rgs)


def _first_result(obj):
    """构造 db.execute 返回值：result.scalars().first() -> obj。"""
    result = MagicMock()
    result.scalars.return_value.first.return_value = obj
    return result


# ── _safe_load_nodes ────────────────────────────────────────

def test_safe_load_nodes_valid_and_invalid():
    assert QueryPrivService._safe_load_nodes('[{"a": 1}]') == [{"a": 1}]
    assert QueryPrivService._safe_load_nodes("") == []
    assert QueryPrivService._safe_load_nodes("not-json{") == []


# ── _decorate_snapshot_for_applicant ────────────────────────

def test_decorate_snapshot_fills_manager_node_only():
    nodes = [
        {"approver_type": "manager", "node_name": "n1"},
        {"approver_type": "users", "node_name": "n2"},
    ]
    applicant = {"id": 42, "display_name": "Alice", "username": "alice"}

    out = QueryPrivService._decorate_snapshot_for_applicant(nodes, applicant)

    assert out[0]["applicant_id"] == 42
    assert out[0]["applicant_name"] == "Alice"
    assert "applicant_id" not in out[1]
    # 原始输入不被就地修改
    assert "applicant_id" not in nodes[0]


def test_decorate_snapshot_falls_back_to_username():
    nodes = [{"approver_type": "manager"}]
    out = QueryPrivService._decorate_snapshot_for_applicant(nodes, {"id": 1, "username": "bob"})
    assert out[0]["applicant_name"] == "bob"


# ── _get_current_pending_node ───────────────────────────────

def test_get_current_pending_node_picks_first_pending():
    apply = SimpleNamespace(audit_auth_groups_info=json.dumps([
        {"node_name": "a", "status": AuditStatus.PASSED},
        {"node_name": "b", "status": AuditStatus.PENDING},
    ]))
    node = QueryPrivService._get_current_pending_node(apply)
    assert node["node_name"] == "b"


def test_get_current_pending_node_none_when_all_done():
    apply = SimpleNamespace(audit_auth_groups_info=json.dumps([
        {"status": AuditStatus.PASSED},
    ]))
    assert QueryPrivService._get_current_pending_node(apply) is None


# ── can_cancel_apply ────────────────────────────────────────

def test_can_cancel_apply_applicant_before_approval():
    apply = SimpleNamespace(user_id=1, status=0, audit_auth_groups_info="[]")
    assert QueryPrivService.can_cancel_apply(apply, {"id": 1}) is True


def test_can_cancel_apply_blocked_when_not_pending():
    apply = SimpleNamespace(user_id=1, status=1, audit_auth_groups_info="[]")
    assert QueryPrivService.can_cancel_apply(apply, {"id": 1}) is False


def test_can_cancel_apply_blocked_for_other_user():
    apply = SimpleNamespace(user_id=1, status=0, audit_auth_groups_info="[]")
    assert QueryPrivService.can_cancel_apply(apply, {"id": 2}) is False


# ── user_has_instance_access ────────────────────────────────

def test_instance_access_superuser_and_global_perm():
    inst = _instance(rg_ids=[9])
    assert QueryPrivService.user_has_instance_access({"is_superuser": True}, inst) is True
    assert QueryPrivService.user_has_instance_access(
        {"permissions": ["query_all_instances"]}, inst
    ) is True


def test_instance_access_by_resource_group_intersection():
    inst = _instance(rg_ids=[1, 2])
    assert QueryPrivService.user_has_instance_access({"resource_groups": [2]}, inst) is True
    assert QueryPrivService.user_has_instance_access({"resource_groups": [5]}, inst) is False


# ── user_has_query_bypass / query_bypass_reason ─────────────

def test_query_bypass_admin_and_global():
    inst = _instance(rg_ids=[1])
    assert QueryPrivService.user_has_query_bypass({"is_superuser": True}, inst) is True
    assert QueryPrivService.query_bypass_reason({"is_superuser": True}, inst) == "admin"


def test_query_bypass_requires_resource_group_permission():
    inst = _instance(rg_ids=[1])
    # 有 rg 交集但缺权限 -> 不可绕过
    assert QueryPrivService.user_has_query_bypass({"resource_groups": [1]}, inst) is False
    user = {"permissions": ["query_resource_group_instance"], "resource_groups": [1]}
    assert QueryPrivService.user_has_query_bypass(user, inst) is True
    assert QueryPrivService.query_bypass_reason(user, inst) == "resource_group_query"


def test_query_bypass_reason_empty_when_no_path():
    inst = _instance(rg_ids=[1])
    assert QueryPrivService.query_bypass_reason({"resource_groups": [9]}, inst) == ""


# ── _normalize_scope_type ───────────────────────────────────

def test_normalize_scope_type_variants():
    assert QueryPrivService._normalize_scope_type("instance") == ("instance", 0)
    assert QueryPrivService._normalize_scope_type("table") == ("table", 2)
    assert QueryPrivService._normalize_scope_type(None, table_name="t") == ("table", 2)
    assert QueryPrivService._normalize_scope_type("database") == ("database", 1)
    assert QueryPrivService._normalize_scope_type(None, db_name="d") == ("database", 1)
    assert QueryPrivService._normalize_scope_type(None) == ("database", 1)


# ── _pg_table_candidates ────────────────────────────────────

def test_pg_table_candidates():
    assert QueryPrivService._pg_table_candidates("public", "t") == ["t", "public.t"]
    assert QueryPrivService._pg_table_candidates("", "t") == ["t"]
    assert QueryPrivService._pg_table_candidates("public", "") == []


# ── _normalize_table_lookup_names ───────────────────────────

def test_normalize_table_lookup_empty_returns_empty():
    assert QueryPrivService._normalize_table_lookup_names(_instance(), "d", "  ") == []


def test_normalize_table_lookup_pgsql_qualified():
    inst = _instance(db_type="pgsql")
    assert QueryPrivService._normalize_table_lookup_names(inst, "d", "public.t") == ["t", "public.t"]


def test_normalize_table_lookup_non_pgsql_with_db():
    inst = _instance(db_type="mysql")
    assert QueryPrivService._normalize_table_lookup_names(inst, "shop", "orders") == [
        "orders", "shop.orders",
    ]


def test_normalize_table_lookup_plain():
    inst = _instance(db_type="mysql")
    assert QueryPrivService._normalize_table_lookup_names(inst, "", "orders") == ["orders"]


# ── 三级授权探测（AsyncMock DB） ─────────────────────────────

@pytest.mark.asyncio
async def test_has_instance_priv_true_false():
    db = AsyncMock()
    db.execute.return_value = _first_result(object())
    assert await QueryPrivService._has_instance_priv(db, 1, 2) is True

    db.execute.return_value = _first_result(None)
    assert await QueryPrivService._has_instance_priv(db, 1, 2) is False


@pytest.mark.asyncio
async def test_has_db_priv_short_circuits_on_instance_priv():
    db = AsyncMock()
    db.execute.return_value = _first_result(object())  # instance 级命中
    assert await QueryPrivService._has_db_priv(db, 1, 2, "shop") is True
    # 命中 instance 级即返回，不再查 database 级
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_has_db_priv_falls_through_to_database_scope():
    db = AsyncMock()
    db.execute.side_effect = [_first_result(None), _first_result(object())]
    assert await QueryPrivService._has_db_priv(db, 1, 2, "shop") is True
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_has_table_priv_empty_names_after_instance_miss():
    db = AsyncMock()
    db.execute.return_value = _first_result(None)  # 无 instance 级
    assert await QueryPrivService._has_table_priv(db, 1, 2, "shop", ["  ", ""]) is False
    # 表名归一化后为空，直接返回，不再发第二次查询
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_has_table_priv_hits_named_table():
    db = AsyncMock()
    db.execute.side_effect = [_first_result(None), _first_result(object())]
    assert await QueryPrivService._has_table_priv(db, 1, 2, "shop", ["orders"]) is True


@pytest.mark.asyncio
async def test_has_any_table_priv_in_db_and_data_dict():
    db = AsyncMock()
    db.execute.side_effect = [_first_result(None), _first_result(object())]
    assert await QueryPrivService._has_any_table_priv_in_db(db, 1, 2, "shop") is True

    db2 = AsyncMock()
    db2.execute.return_value = _first_result(None)
    assert await QueryPrivService._has_any_data_dict_priv(db2, 1, 2) is False
