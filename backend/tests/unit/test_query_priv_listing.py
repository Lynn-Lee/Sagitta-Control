"""`QueryPrivService` 有效 limit 计算、pg search_path 归并与权限列表单测。

以 AsyncMock 隔离 DB、monkeypatch 固定 GovernanceScope 与探测结果，
覆盖 limit 取最小、pgsql schema 解析、我的权限与管理权限列表构造。
"""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.query_priv import QueryPrivService as QP

DATA_USER = {"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False}
BYPASS_USER = {"id": 7, "permissions": ["query_all_instances"], "resource_groups": [], "is_superuser": False}


def _instance(db_type: str = "mysql") -> SimpleNamespace:
    return SimpleNamespace(id=1, db_type=db_type, resource_groups=[SimpleNamespace(id=2)])


def _first(obj) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = obj
    return result


def _all(rows) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _priv(limit_num: int | None) -> SimpleNamespace | None:
    return None if limit_num is None else SimpleNamespace(limit_num=limit_num)


# ── get_effective_query_limit ───────────────────────────────

@pytest.mark.asyncio
async def test_limit_bypass_returns_requested():
    out = await QP.get_effective_query_limit(
        AsyncMock(), BYPASS_USER, _instance(), "d", "SELECT 1", requested_limit=999, table_refs=[]
    )
    assert out == 999


@pytest.mark.asyncio
async def test_limit_no_tables_takes_min_of_db_and_instance():
    db = AsyncMock()
    # 顺序：instance_limit -> database_limit
    db.execute.side_effect = [_first(_priv(500)), _first(_priv(200))]
    out = await QP.get_effective_query_limit(
        db, DATA_USER, _instance(), "shop", "SELECT 1", requested_limit=1000, table_refs=[]
    )
    assert out == 200


@pytest.mark.asyncio
async def test_limit_no_tables_falls_back_to_requested():
    db = AsyncMock()
    db.execute.side_effect = [_first(None), _first(None)]
    out = await QP.get_effective_query_limit(
        db, DATA_USER, _instance(), "shop", "SELECT 1", requested_limit=100, table_refs=[]
    )
    assert out == 100


@pytest.mark.asyncio
async def test_limit_mysql_table_scope_caps_requested():
    db = AsyncMock()
    # instance_limit(None) -> table_limit(50)
    db.execute.side_effect = [_first(None), _first(_priv(50))]
    out = await QP.get_effective_query_limit(
        db, DATA_USER, _instance(), "shop", "SELECT * FROM orders",
        requested_limit=1000, table_refs=[{"name": "orders", "schema": ""}],
    )
    assert out == 50


@pytest.mark.asyncio
async def test_limit_mysql_table_falls_back_to_instance():
    db = AsyncMock()
    # instance_limit(300) -> table(None) -> database(None) -> 回退 instance 300
    db.execute.side_effect = [_first(_priv(300)), _first(None), _first(None)]
    out = await QP.get_effective_query_limit(
        db, DATA_USER, _instance(), "shop", "SELECT * FROM orders",
        requested_limit=1000, table_refs=[{"name": "orders", "schema": ""}],
    )
    assert out == 300


# ── resolve_pg_search_path ──────────────────────────────────

@pytest.mark.asyncio
async def test_search_path_non_pgsql_none():
    assert await QP.resolve_pg_search_path(_instance("mysql"), "d", "SELECT 1", table_refs=[]) is None


@pytest.mark.asyncio
async def test_search_path_no_tables_none():
    assert await QP.resolve_pg_search_path(_instance("pgsql"), "d", "SELECT 1", table_refs=[]) is None


@pytest.mark.asyncio
async def test_search_path_explicit_schema_appends_public():
    out = await QP.resolve_pg_search_path(
        _instance("pgsql"), "d", "SELECT * FROM s.t", table_refs=[{"schema": "s", "name": "t"}]
    )
    assert out == "s,public"


@pytest.mark.asyncio
async def test_search_path_resolved_single_schema(monkeypatch):
    monkeypatch.setattr(QP, "_get_pg_table_schema_map", AsyncMock(return_value={"t": ["app"]}))
    out = await QP.resolve_pg_search_path(
        _instance("pgsql"), "d", "SELECT * FROM t", table_refs=[{"schema": "", "name": "t"}]
    )
    assert out == "app,public"


@pytest.mark.asyncio
async def test_search_path_ambiguous_returns_none(monkeypatch):
    monkeypatch.setattr(QP, "_get_pg_table_schema_map", AsyncMock(return_value={"t": ["a", "b"]}))
    out = await QP.resolve_pg_search_path(
        _instance("pgsql"), "d", "SELECT * FROM t", table_refs=[{"schema": "", "name": "t"}]
    )
    assert out is None


# ── list_my_privileges ──────────────────────────────────────

@pytest.mark.asyncio
async def test_list_my_privileges_returns_rows():
    db = AsyncMock()
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    db.execute.return_value = _all(rows)
    out = await QP.list_my_privileges(db, user_id=7)
    assert out == rows


@pytest.mark.asyncio
async def test_list_my_privileges_instance_filter():
    db = AsyncMock()
    db.execute.return_value = _all([SimpleNamespace(id=3)])
    out = await QP.list_my_privileges(db, user_id=7, instance_id=1)
    assert len(out) == 1


# ── list_manage_privileges ──────────────────────────────────

@pytest.mark.asyncio
async def test_list_manage_privileges_builds_items(monkeypatch):
    monkeypatch.setattr(
        "app.services.governance_scope.GovernanceScopeService.resolve",
        AsyncMock(return_value={"mode": "all", "label": "全部"}),
    )
    monkeypatch.setattr(
        "app.services.governance_scope.GovernanceScopeService.apply_scope",
        lambda stmt, scope, **kw: stmt,
    )
    monkeypatch.setattr(QP, "_can_revoke_privilege", AsyncMock(return_value=True))

    priv = SimpleNamespace(
        id=11, user_id=7, instance_id=1, db_name="shop", table_name="orders",
        scope_type="table", valid_date=date(2099, 1, 1), limit_num=100, priv_type=1,
        created_at=datetime(2026, 1, 1), revoked_at=None, revoked_by_id=None,
        revoked_by_name=None, revoke_reason=None,
    )
    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    rows_result = MagicMock()
    rows_result.all.return_value = [(priv, "alice", "Alice", "prod-db")]
    db.execute.side_effect = [count_result, rows_result]

    meta, total, items = await QP.list_manage_privileges(db, DATA_USER)

    assert meta == {"mode": "all", "label": "全部"}
    assert total == 1
    assert len(items) == 1
    item = items[0]
    assert item["id"] == 11
    assert item["user_display"] == "Alice"
    assert item["instance_name"] == "prod-db"
    assert item["can_revoke"] is True
    assert item["revoked_at"] == ""  # None -> 空串
