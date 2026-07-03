"""会话诊断接口资源组隔离集成测试。"""

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.database import get_db
from app.core.deps import current_user
from app.engines.models import ResultSet
from app.main import app
from app.models.instance import Instance
from app.models.user import ResourceGroup


async def _create_instance_with_resource_group(group_id: int) -> int:
    override_get_db = app.dependency_overrides[get_db]
    session_gen: AsyncGenerator = override_get_db()
    db = await session_gen.__anext__()
    try:
        rg = ResourceGroup(
            id=group_id,
            group_name=f"rg-{group_id}",
            group_name_cn=f"资源组 {group_id}",
            is_active=True,
        )
        inst = Instance(
            instance_name=f"diag-mysql-{group_id}",
            type="master",
            db_type="mysql",
            host="127.0.0.1",
            port=3306,
            user="root",
            password="secret",
            is_active=True,
            resource_groups=[rg],
        )
        db.add(inst)
        await db.commit()
        await db.refresh(inst)
        return inst.id
    finally:
        await session_gen.aclose()


def _override_user(user: dict):
    async def _current_user_override() -> dict:
        return user

    app.dependency_overrides[current_user] = _current_user_override


class _FakeEngine:
    def __init__(self):
        self.killed_thread_ids: list[int] = []

    async def kill_connection(self, thread_id: int) -> ResultSet:
        self.killed_thread_ids.append(thread_id)
        return ResultSet()


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    yield
    app.dependency_overrides.pop(current_user, None)


@pytest.mark.asyncio
async def test_kill_session_rejects_instance_outside_user_resource_group(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    instance_id = await _create_instance_with_resource_group(group_id=20)
    fake_engine = _FakeEngine()
    _override_user(
        {
            "id": 7,
            "username": "dba-group-a",
            "is_superuser": False,
            "permissions": ["observability_session_kill"],
            "resource_groups": [10],
        }
    )
    monkeypatch.setattr("app.routers.diagnostic.get_engine", lambda _inst: fake_engine)

    resp = await client.post(
        f"/api/v1/diagnostic/kill/?instance_id={instance_id}&thread_id=123"
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "实例不在你的资源组内"
    assert fake_engine.killed_thread_ids == []


@pytest.mark.asyncio
async def test_kill_session_allows_observability_global_permission(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    instance_id = await _create_instance_with_resource_group(group_id=20)
    fake_engine = _FakeEngine()
    _override_user(
        {
            "id": 8,
            "username": "global-observer",
            "is_superuser": False,
            "permissions": ["observability_session_kill", "observability_instance_all"],
            "resource_groups": [10],
        }
    )
    monkeypatch.setattr("app.routers.diagnostic.get_engine", lambda _inst: fake_engine)

    async def _write_audit_log(**_kwargs):
        return None

    monkeypatch.setattr("app.routers.diagnostic.AuditLogService.write", _write_audit_log)

    resp = await client.post(
        f"/api/v1/diagnostic/kill/?instance_id={instance_id}&thread_id=123"
    )

    assert resp.status_code == 200
    assert fake_engine.killed_thread_ids == [123]
