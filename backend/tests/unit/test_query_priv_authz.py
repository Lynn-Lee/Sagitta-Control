"""`QueryPrivService` 查询/数据字典授权判定单测。

聚焦三层校验的分支：绕过、资源组范围、数据级（database/table）授权，
以及 pgsql schema 消歧。以 monkeypatch 固定 `_has_*` 探测结果隔离 DB。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.query_priv import QueryPrivService as QP

# 数据层用户：在资源组 2 内、无任何绕过权限
DATA_USER = {"id": 7, "permissions": [], "resource_groups": [2], "is_superuser": False}
BYPASS_USER = {"id": 7, "permissions": ["query_all_instances"], "resource_groups": [], "is_superuser": False}
OUTSIDER = {"id": 7, "permissions": [], "resource_groups": [9], "is_superuser": False}


def _instance(db_type: str = "mysql") -> SimpleNamespace:
    return SimpleNamespace(id=1, db_type=db_type, resource_groups=[SimpleNamespace(id=2)])


def _privs_result(privs: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = privs
    return result


def _patch_has(monkeypatch, **flags):
    """monkeypatch QueryPrivService._has_* 系列为固定布尔。"""
    for name, value in flags.items():
        monkeypatch.setattr(QP, name, AsyncMock(return_value=value))


# ── list_data_dict_databases ────────────────────────────────

@pytest.mark.asyncio
async def test_list_databases_bypass_returns_all():
    out = await QP.list_data_dict_databases(AsyncMock(), BYPASS_USER, _instance(), ["a", "b"])
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_list_databases_outsider_returns_empty():
    out = await QP.list_data_dict_databases(AsyncMock(), OUTSIDER, _instance(), ["a", "b"])
    assert out == []


@pytest.mark.asyncio
async def test_list_databases_instance_priv_returns_all(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=True)
    out = await QP.list_data_dict_databases(AsyncMock(), DATA_USER, _instance(), ["a", "b"])
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_list_databases_filters_to_scoped(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False)
    db = AsyncMock()
    db.execute.return_value = _privs_result([
        SimpleNamespace(db_name="a"), SimpleNamespace(db_name=" "), SimpleNamespace(db_name=None),
    ])
    out = await QP.list_data_dict_databases(db, DATA_USER, _instance(), ["a", "b"])
    assert out == ["a"]


# ── list_data_dict_tables ───────────────────────────────────

@pytest.mark.asyncio
async def test_list_tables_bypass_and_outsider():
    assert await QP.list_data_dict_tables(AsyncMock(), BYPASS_USER, _instance(), "d", ["t"]) == ["t"]
    assert await QP.list_data_dict_tables(AsyncMock(), OUTSIDER, _instance(), "d", ["t"]) == []


@pytest.mark.asyncio
async def test_list_tables_db_priv_returns_all(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_db_priv=True)
    out = await QP.list_data_dict_tables(AsyncMock(), DATA_USER, _instance(), "d", ["t1", "t2"])
    assert out == ["t1", "t2"]


@pytest.mark.asyncio
async def test_list_tables_appends_extra_granted_tables(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_db_priv=False)
    db = AsyncMock()
    db.execute.return_value = _privs_result([
        SimpleNamespace(table_name="orders"), SimpleNamespace(table_name="secret"),
    ])
    # 请求可见 orders；secret 虽未被请求但已授权，追加到末尾
    out = await QP.list_data_dict_tables(db, DATA_USER, _instance(), "d", ["orders", "public_only"])
    assert out == ["orders", "secret"]


# ── check_data_dict_access ──────────────────────────────────

@pytest.mark.asyncio
async def test_check_data_dict_outsider():
    ok, reason = await QP.check_data_dict_access(AsyncMock(), OUTSIDER, _instance())
    assert ok is False
    assert reason == "实例不在你的资源组内"


@pytest.mark.asyncio
async def test_check_data_dict_no_db_scoped_priv(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_any_data_dict_priv=False)
    ok, reason = await QP.check_data_dict_access(AsyncMock(), DATA_USER, _instance())
    assert ok is False
    assert "请先申请查询权限" in reason


@pytest.mark.asyncio
async def test_check_data_dict_table_privilege(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_db_priv=False, _has_table_priv=True)
    ok, reason = await QP.check_data_dict_access(
        AsyncMock(), DATA_USER, _instance(), db_name="shop", table_name="orders"
    )
    assert ok is True
    assert reason == "table_privilege"


# ── check_query_priv ────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_query_priv_bypass():
    ok, reason = await QP.check_query_priv(AsyncMock(), BYPASS_USER, _instance(), "d", "SELECT 1")
    assert ok is True
    assert reason == "admin"


@pytest.mark.asyncio
async def test_check_query_priv_outsider():
    ok, reason = await QP.check_query_priv(AsyncMock(), OUTSIDER, _instance(), "d", "SELECT 1")
    assert ok is False


@pytest.mark.asyncio
async def test_check_query_priv_no_tables_db_priv(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_db_priv=True)
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance(), "shop", "SELECT 1", table_refs=[]
    )
    assert ok is True
    assert reason == "db_privilege"


@pytest.mark.asyncio
async def test_check_query_priv_no_tables_denied(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=False, _has_db_priv=False)
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance(), "shop", "SELECT 1", table_refs=[]
    )
    assert ok is False
    assert "没有数据库 shop 的查询权限" in reason


@pytest.mark.asyncio
async def test_check_query_priv_mysql_table_granted(monkeypatch):
    _patch_has(monkeypatch, _has_db_priv=False, _has_table_priv=True)
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance(), "shop", "SELECT * FROM orders",
        table_refs=[{"name": "orders", "schema": ""}],
    )
    assert ok is True
    assert reason == "privilege"


@pytest.mark.asyncio
async def test_check_query_priv_mysql_table_denied(monkeypatch):
    _patch_has(monkeypatch, _has_db_priv=False, _has_table_priv=False)
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance(), "shop", "SELECT * FROM orders",
        table_refs=[{"name": "orders", "schema": ""}],
    )
    assert ok is False
    assert "没有表 shop.orders 的查询权限" in reason


@pytest.mark.asyncio
async def test_check_query_priv_pgsql_ambiguous_schema(monkeypatch):
    _patch_has(monkeypatch, _has_db_priv=False)
    monkeypatch.setattr(
        QP, "_get_pg_table_schema_map", AsyncMock(return_value={"orders": ["s1", "s2"]})
    )
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance("pgsql"), "shop", "SELECT * FROM orders",
        table_refs=[{"name": "orders", "schema": ""}],
    )
    assert ok is False
    assert "在多个 schema 中存在" in reason


@pytest.mark.asyncio
async def test_check_query_priv_pgsql_explicit_schema_granted(monkeypatch):
    _patch_has(monkeypatch, _has_db_priv=False, _has_table_priv=True)
    monkeypatch.setattr(QP, "_get_pg_table_schema_map", AsyncMock(return_value={}))
    ok, reason = await QP.check_query_priv(
        AsyncMock(), DATA_USER, _instance("pgsql"), "shop", "SELECT * FROM public.orders",
        table_refs=[{"name": "orders", "schema": "public"}],
    )
    assert ok is True


# ── explain_query_access ────────────────────────────────────

@pytest.mark.asyncio
async def test_explain_layer_identity_for_admin():
    out = await QP.explain_query_access(AsyncMock(), BYPASS_USER, _instance(), "d", "SELECT 1")
    assert out["allowed"] is True
    assert out["layer"] == "identity"


@pytest.mark.asyncio
async def test_explain_layer_resource_scope_for_outsider():
    out = await QP.explain_query_access(AsyncMock(), OUTSIDER, _instance(), "d", "SELECT 1")
    assert out["allowed"] is False
    assert out["layer"] == "resource_scope"


@pytest.mark.asyncio
async def test_explain_layer_data_scope(monkeypatch):
    _patch_has(monkeypatch, _has_instance_priv=True)
    out = await QP.explain_query_access(
        AsyncMock(), DATA_USER, _instance(), "shop", "SELECT 1", table_refs=[]
    )
    assert out["layer"] == "data_scope"
