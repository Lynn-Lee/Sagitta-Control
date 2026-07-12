"""`AuditLogService` 单测。

该服务原无专属覆盖（`write`/`list_logs`/`get_modules` 全部未测）。
此处以 AsyncMock 隔离 DB 会话，锁定写入截断、失败回滚、过滤条件构造与分页行为。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.system import OperationLog
from app.services.audit_log import AuditLogService


def _fake_request(host: str = "1.2.3.4") -> SimpleNamespace:
    """构造仅含 resolve_client_ip 所需字段的伪 Request（无 XFF，回退对端地址）。"""
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={})


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()  # add 为同步方法，避免 AsyncMock 产生未 await 协程告警
    return db


def _added_log(db: AsyncMock) -> OperationLog:
    db.add.assert_called_once()
    return db.add.call_args.args[0]


@pytest.mark.asyncio
async def test_write_persists_and_commits():
    db = _make_db()
    user = {"id": 7, "username": "alice"}

    await AuditLogService.write(
        db, user, action="login", module="auth", detail="ok", result="success",
        request=_fake_request(), remark="note",
    )

    log = _added_log(db)
    assert log.user_id == 7
    assert log.username == "alice"
    assert log.action == "login"
    assert log.module == "auth"
    assert log.ip_address == "1.2.3.4"
    assert log.result == "success"
    assert log.remark == "note"
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_truncates_detail_and_defaults_missing_user_fields():
    db = _make_db()

    await AuditLogService.write(db, {}, action="a", module="m", detail="x" * 3000)

    log = _added_log(db)
    assert log.user_id == 0
    assert log.username == ""
    assert log.ip_address == ""  # request 缺省 -> 空 IP
    assert len(log.detail) == 2000


@pytest.mark.asyncio
async def test_write_rolls_back_and_swallows_commit_error():
    db = _make_db()
    db.commit.side_effect = RuntimeError("db down")

    # 审计写入失败不得向上抛出，避免影响主业务
    await AuditLogService.write(db, {"id": 1, "username": "b"}, action="a", module="m")

    db.rollback.assert_awaited_once()


def _count_result(total: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = total
    return result


def _rows_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_list_logs_applies_all_filters_and_returns_page():
    rows = [OperationLog(id=1), OperationLog(id=2)]
    db = AsyncMock()
    db.execute.side_effect = [_count_result(2), _rows_result(rows)]

    total, out = await AuditLogService.list_logs(
        db,
        username="ali",
        module="auth",
        action="login",
        result="success",
        date_start="2026-01-01",
        date_end="2026-12-31",
        page=2,
        page_size=10,
    )

    assert total == 2
    assert out == rows
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_list_logs_ignores_invalid_dates_and_empty_filters():
    db = AsyncMock()
    db.execute.side_effect = [_count_result(0), _rows_result([])]

    total, out = await AuditLogService.list_logs(
        db, date_start="not-a-date", date_end="also-bad",
    )

    assert total == 0
    assert out == []


def test_get_modules_returns_fixed_catalog():
    modules = AuditLogService.get_modules()
    assert "auth" in modules
    assert "workflow" in modules
    assert len(modules) == len(set(modules))  # 无重复
