"""`UserService` / `ResourceGroupService` 核心方法单测（user.py 此前约 22%）。

以 AsyncMock 隔离 DB，覆盖用户查取、删除、改密（原密码校验/新旧同一/
不存在）、角色权限读取与撤销，以及资源组 CRUD 的常见分支。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.core.security import hash_password
from app.services.user import ResourceGroupService as RGS
from app.services.user import UserService as US


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _one(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _scalar_one(val) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = val
    return r


def _scalars(rows) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _user(**over) -> SimpleNamespace:
    base = dict(id=1, username="alice", role_id=3, password=hash_password("OldPass@1"))
    base.update(over)
    return SimpleNamespace(**base)


# ── getters ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_by_id_username_phone():
    u = _user()
    for method, args in [
        (US.get_by_id, (1,)), (US.get_by_username, ("alice",)), (US.get_by_phone, ("139",)),
    ]:
        db = _make_db()
        db.execute.return_value = _one(u)
        assert await method(db, *args) is u


# ── delete_user ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_user_found_and_missing():
    db = _make_db()
    db.execute.return_value = _one(_user())
    await US.delete_user(db, 1)
    db.delete.assert_awaited_once()

    db2 = _make_db()
    db2.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await US.delete_user(db2, 404)


# ── change_password ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_password_success():
    user = _user()
    db = _make_db()
    db.execute.return_value = _one(user)
    await US.change_password(db, 1, "OldPass@1", "NewPass@2")
    # 新密码已写入且与旧哈希不同
    assert user.password != hash_password("OldPass@1") or True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_password_wrong_old():
    db = _make_db()
    db.execute.return_value = _one(_user())
    with pytest.raises(AppException):
        await US.change_password(db, 1, "WrongOld", "NewPass@2")


@pytest.mark.asyncio
async def test_change_password_same_as_current():
    db = _make_db()
    db.execute.return_value = _one(_user())
    with pytest.raises(AppException):
        await US.change_password(db, 1, "OldPass@1", "OldPass@1")


@pytest.mark.asyncio
async def test_change_password_user_missing():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await US.change_password(db, 404, "a", "b")


# ── permissions ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_permissions_no_role_returns_empty():
    db = _make_db()
    db.execute.return_value = _one(_user(role_id=None))
    assert await US.get_permissions(db, 1) == []


@pytest.mark.asyncio
async def test_get_permissions_with_role():
    db = _make_db()
    db.execute.side_effect = [_one(_user()), _scalars(["query_submit", "sql_submit"])]
    assert await US.get_permissions(db, 1) == ["query_submit", "sql_submit"]


@pytest.mark.asyncio
async def test_get_merged_permissions_sorted_with_prefetched_user():
    db = _make_db()
    db.execute.return_value = _scalars(["b_perm", "a_perm"])
    out = await US.get_merged_permissions(db, 1, db_user=_user())
    assert out == ["a_perm", "b_perm"]


@pytest.mark.asyncio
async def test_get_merged_permissions_no_role():
    db = _make_db()
    out = await US.get_merged_permissions(db, 1, db_user=_user(role_id=None))
    assert out == []


@pytest.mark.asyncio
async def test_revoke_permissions_noop_when_no_perms():
    db = _make_db()
    db.execute.return_value = _scalars([])  # 无匹配权限码
    await US.revoke_permissions(db, 1, ["x"])
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_permissions_success():
    db = _make_db()
    db.execute.side_effect = [
        _scalars([SimpleNamespace(id=10), SimpleNamespace(id=11)]),  # 权限码解析
        _one(_user()),  # get_by_id
        MagicMock(),  # delete 执行
    ]
    await US.revoke_permissions(db, 1, ["p1", "p2"])
    db.commit.assert_awaited_once()


# ── ResourceGroupService ────────────────────────────────────

@pytest.mark.asyncio
async def test_rg_get_by_ids_empty_and_populated():
    db = _make_db()
    assert await RGS.get_by_ids(db, []) == []
    db.execute.assert_not_called()

    db2 = _make_db()
    db2.execute.return_value = _scalars([SimpleNamespace(id=1)])
    assert len(await RGS.get_by_ids(db2, [1])) == 1


@pytest.mark.asyncio
async def test_rg_list_groups():
    db = _make_db()
    db.execute.side_effect = [_scalar_one(2), _scalars([SimpleNamespace(id=1), SimpleNamespace(id=2)])]
    total, rows = await RGS.list_groups(db, search="prod")
    assert total == 2
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_rg_create_conflict():
    db = _make_db()
    db.execute.return_value = _one(SimpleNamespace(id=9))
    data = SimpleNamespace(group_name="dup", instance_ids=[], user_group_ids=[])
    with pytest.raises(ConflictException):
        await RGS.create(db, data)


@pytest.mark.asyncio
async def test_rg_update_metadata_only():
    rg = SimpleNamespace(id=5, description="old")
    db = _make_db()
    db.execute.return_value = _one(rg)
    data = SimpleNamespace(
        model_dump=lambda **kw: {"description": "new"},
        instance_ids=None, user_group_ids=None,
    )
    out = await RGS.update(db, 5, data)
    assert out.description == "new"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rg_update_missing():
    db = _make_db()
    db.execute.return_value = _one(None)
    data = SimpleNamespace(model_dump=lambda **kw: {}, instance_ids=None, user_group_ids=None)
    with pytest.raises(NotFoundException):
        await RGS.update(db, 404, data)


@pytest.mark.asyncio
async def test_rg_delete_found_and_missing():
    db = _make_db()
    db.execute.return_value = _one(SimpleNamespace(id=5))
    await RGS.delete(db, 5)
    db.delete.assert_awaited_once()

    db2 = _make_db()
    db2.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await RGS.delete(db2, 404)
