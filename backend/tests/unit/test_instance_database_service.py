"""`InstanceDatabaseService` 单测（此前约 17% 覆盖）。

以 AsyncMock 隔离 DB、monkeypatch get_engine 隔离引擎，覆盖数据库注册的
增删改查、label 归类，以及从引擎同步（redis 固定、引擎报错、异常、
新增/更新/移除三态与系统库 remark 复位）。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.services.instance_database import InstanceDatabaseService


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _one(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalars(rows) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _idb(db_name: str, remark: str = "", is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, db_name=db_name, remark=remark, is_active=is_active, sync_at=None,
    )


# ── get_db_label ────────────────────────────────────────────

def test_get_db_label_variants():
    assert InstanceDatabaseService.get_db_label("oracle") == "Schema"
    assert InstanceDatabaseService.get_db_label("redis") == "数据库编号"
    assert InstanceDatabaseService.get_db_label("mysql") == "数据库"


# ── list_databases ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_databases_with_label():
    db = _make_db()
    db.execute.side_effect = [
        _scalars([_idb("shop")]),
        _one(SimpleNamespace(db_type="oracle")),
    ]
    out = await InstanceDatabaseService.list_databases(db, instance_id=1)
    assert out[0]["db_name"] == "shop"
    assert out[0]["db_name_label"] == "Schema"


@pytest.mark.asyncio
async def test_list_databases_default_label_when_no_instance():
    db = _make_db()
    db.execute.side_effect = [_scalars([]), _one(None)]
    out = await InstanceDatabaseService.list_databases(db, instance_id=1, include_inactive=True)
    assert out == []


# ── add_database ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_database_missing_instance():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await InstanceDatabaseService.add_database(db, 1, "shop")


@pytest.mark.asyncio
async def test_add_database_conflict():
    db = _make_db()
    db.execute.side_effect = [_one(SimpleNamespace(id=1)), _one(_idb("shop"))]
    with pytest.raises(ConflictException):
        await InstanceDatabaseService.add_database(db, 1, "shop")


@pytest.mark.asyncio
async def test_add_database_success_strips_name():
    db = _make_db()
    db.execute.side_effect = [_one(SimpleNamespace(id=1)), _one(None)]
    idb = await InstanceDatabaseService.add_database(db, 1, "  shop  ", remark="备注")
    assert idb.db_name == "shop"
    db.commit.assert_awaited_once()


# ── update_database / delete_database ───────────────────────

@pytest.mark.asyncio
async def test_update_database_sets_fields():
    idb = _idb("shop")
    db = _make_db()
    db.execute.return_value = _one(idb)
    out = await InstanceDatabaseService.update_database(db, 1, remark="新", is_active=False)
    assert out.remark == "新"
    assert out.is_active is False


@pytest.mark.asyncio
async def test_update_database_missing():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await InstanceDatabaseService.update_database(db, 404)


@pytest.mark.asyncio
async def test_delete_database_found_and_missing():
    db = _make_db()
    db.execute.return_value = _one(_idb("shop"))
    await InstanceDatabaseService.delete_database(db, 1)
    db.delete.assert_awaited_once()

    db2 = _make_db()
    db2.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await InstanceDatabaseService.delete_database(db2, 404)


# ── sync_from_engine ────────────────────────────────────────

def _patch_engine(monkeypatch, engine):
    monkeypatch.setattr("app.services.instance_database.get_engine", lambda inst: engine)


@pytest.mark.asyncio
async def test_sync_missing_instance():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await InstanceDatabaseService.sync_from_engine(db, 1)


@pytest.mark.asyncio
async def test_sync_redis_uses_fixed_range(monkeypatch):
    db = _make_db()
    db.execute.side_effect = [
        _one(SimpleNamespace(id=1, db_type="redis")),
        _scalars([]),
    ]
    _patch_engine(monkeypatch, SimpleNamespace())
    out = await InstanceDatabaseService.sync_from_engine(db, 1)
    assert out["success"] is True
    assert out["total"] == 16
    assert out["added"] == 16


@pytest.mark.asyncio
async def test_sync_engine_error_returns_failure(monkeypatch):
    db = _make_db()
    db.execute.return_value = _one(SimpleNamespace(id=1, db_type="mysql"))
    engine = SimpleNamespace(
        get_all_databases=AsyncMock(return_value=SimpleNamespace(error="连不上", rows=[]))
    )
    _patch_engine(monkeypatch, engine)
    out = await InstanceDatabaseService.sync_from_engine(db, 1)
    assert out["success"] is False
    assert "连接失败" in out["message"]


@pytest.mark.asyncio
async def test_sync_engine_exception_returns_failure(monkeypatch):
    db = _make_db()
    db.execute.return_value = _one(SimpleNamespace(id=1, db_type="mysql"))
    engine = SimpleNamespace(get_all_databases=AsyncMock(side_effect=RuntimeError("boom")))
    _patch_engine(monkeypatch, engine)
    out = await InstanceDatabaseService.sync_from_engine(db, 1)
    assert out["success"] is False
    assert "查询失败" in out["message"]


@pytest.mark.asyncio
async def test_sync_add_update_remove_tristate(monkeypatch):
    db = _make_db()
    existing = [
        _idb("db1", remark="系统库（默认禁用）", is_active=False),  # 仍可见 -> 更新并复位
        _idb("old"),  # 不再可见 -> 移除
    ]
    db.execute.side_effect = [
        _one(SimpleNamespace(id=1, db_type="mysql")),
        _scalars(existing),
    ]
    engine = SimpleNamespace(
        get_all_databases=AsyncMock(
            return_value=SimpleNamespace(error=None, rows=["db1", "db2"])
        )
    )
    _patch_engine(monkeypatch, engine)

    out = await InstanceDatabaseService.sync_from_engine(db, 1)

    assert out == {
        "success": True,
        "message": out["message"],
        "added": 1,
        "updated": 1,
        "removed": 1,
        "total": 2,
    }
    # 系统库 remark 被复位、启用
    assert existing[0].remark == ""
    assert existing[0].is_active is True
    db.delete.assert_awaited_once()
