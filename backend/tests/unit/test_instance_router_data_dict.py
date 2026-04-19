"""
实例路由中的数据字典接口测试。

覆盖：
- /columns
- /constraints
- /indexes
"""

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.deps import current_user
from app.main import app
from app.routers import instance as instance_router


@pytest_asyncio.fixture
async def api_client():
    async def override_get_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def override_current_user():
    async def _user():
        return {
            "id": 1,
            "username": "tester",
            "display_name": "Tester",
            "is_superuser": True,
            "permissions": [],
            "tenant_id": 1,
        }

    app.dependency_overrides[current_user] = _user
    yield
    app.dependency_overrides.pop(current_user, None)


class TestInstanceDataDictRouter:
    @pytest.mark.asyncio
    async def test_get_columns_returns_normalized_payload(
        self, api_client, monkeypatch: pytest.MonkeyPatch, override_current_user
    ):
        monkeypatch.setattr(
            instance_router,
            "_ensure_instance_access",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        get_columns = AsyncMock(
            return_value=[
                {
                    "column_name": "id",
                    "column_type": "bigint(20)",
                    "is_nullable": "NO",
                    "column_default": None,
                    "column_comment": "主键",
                    "column_key": "PRI",
                }
            ]
        )
        monkeypatch.setattr(instance_router.InstanceService, "get_columns", get_columns)

        resp = await api_client.get(
            "/api/v1/instances/1/columns/",
            params={"db_name": "demo", "tb_name": "users"},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "columns": [
                {
                    "column_name": "id",
                    "column_type": "bigint(20)",
                    "is_nullable": "NO",
                    "column_default": None,
                    "column_comment": "主键",
                    "column_key": "PRI",
                }
            ]
        }
        get_columns.assert_awaited_once()
        args = get_columns.await_args.args
        assert args[0] is not None
        assert args[1:] == (1, "demo", "users")

    @pytest.mark.asyncio
    async def test_get_constraints_returns_payload(
        self, api_client, monkeypatch: pytest.MonkeyPatch, override_current_user
    ):
        monkeypatch.setattr(
            instance_router,
            "_ensure_instance_access",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        get_constraints = AsyncMock(
            return_value=[
                {
                    "constraint_name": "PRIMARY",
                    "constraint_type": "PRIMARY KEY",
                    "column_names": "id",
                    "referenced_table_name": "",
                    "referenced_column_names": "",
                }
            ]
        )
        monkeypatch.setattr(instance_router.InstanceService, "get_constraints", get_constraints)

        resp = await api_client.get(
            "/api/v1/instances/1/constraints/",
            params={"db_name": "demo", "tb_name": "users"},
        )

        assert resp.status_code == 200
        assert resp.json()["constraints"][0]["constraint_type"] == "PRIMARY KEY"
        get_constraints.assert_awaited_once_with(ANY, 1, "demo", "users")

    @pytest.mark.asyncio
    async def test_get_indexes_returns_payload(
        self, api_client, monkeypatch: pytest.MonkeyPatch, override_current_user
    ):
        monkeypatch.setattr(
            instance_router,
            "_ensure_instance_access",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        get_indexes = AsyncMock(
            return_value=[
                {
                    "index_name": "idx_user_email",
                    "index_type": "INDEX",
                    "column_names": "email, tenant_id",
                    "is_composite": "YES",
                    "index_comment": "联合索引",
                }
            ]
        )
        monkeypatch.setattr(instance_router.InstanceService, "get_indexes", get_indexes)

        resp = await api_client.get(
            "/api/v1/instances/1/indexes/",
            params={"db_name": "demo", "tb_name": "users"},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "indexes": [
                {
                    "index_name": "idx_user_email",
                    "index_type": "INDEX",
                    "column_names": "email, tenant_id",
                    "is_composite": "YES",
                    "index_comment": "联合索引",
                }
            ]
        }
        get_indexes.assert_awaited_once_with(ANY, 1, "demo", "users")

    @pytest.mark.asyncio
    async def test_get_columns_requires_query_params(
        self, api_client, monkeypatch: pytest.MonkeyPatch, override_current_user
    ):
        monkeypatch.setattr(
            instance_router,
            "_ensure_instance_access",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )

        resp = await api_client.get("/api/v1/instances/1/columns/", params={"db_name": "demo"})

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_indexes_requires_query_params(
        self, api_client, monkeypatch: pytest.MonkeyPatch, override_current_user
    ):
        monkeypatch.setattr(
            instance_router,
            "_ensure_instance_access",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )

        resp = await api_client.get("/api/v1/instances/1/indexes/", params={"tb_name": "users"})

        assert resp.status_code == 422
