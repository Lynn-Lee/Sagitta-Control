"""路由分层泄漏下沉后，被移动到 service 的业务方法单测。

这些端点原先在 router 内直接操作数据库，移动前后均无断言级覆盖；
此处对下沉后的 service 方法补充行为断言，锁定收藏切换与资源组用户组重建逻辑。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundException
from app.services.query_priv import QueryPrivService
from app.services.role import UserGroupService


def _execute_result(scalar):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    return result


@pytest.mark.asyncio
async def test_toggle_favorite_flips_state_and_commits():
    log = SimpleNamespace(is_favorite=False)
    db = AsyncMock()
    db.execute.return_value = _execute_result(log)

    out = await QueryPrivService.toggle_favorite(db, log_id=5, user_id=1)

    assert out is True
    assert log.is_favorite is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_favorite_missing_log_raises():
    db = AsyncMock()
    db.execute.return_value = _execute_result(None)

    with pytest.raises(NotFoundException):
        await QueryPrivService.toggle_favorite(db, log_id=5, user_id=1)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_rg_user_groups_missing_group_raises():
    db = AsyncMock()
    db.execute.return_value = _execute_result(None)

    with pytest.raises(NotFoundException):
        await UserGroupService.update_resource_group_user_groups(db, 9, [1, 2])
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_rg_user_groups_rebuilds_associations_and_commits():
    db = AsyncMock()
    db.execute.return_value = _execute_result(SimpleNamespace(id=9))

    await UserGroupService.update_resource_group_user_groups(db, 9, [1, 2, 3])

    db.commit.assert_awaited_once()
    # 1 次 select 校验 + 1 次 delete 清空 + 3 次 insert 重建 = 5 次 execute
    assert db.execute.await_count == 5
