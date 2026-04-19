"""
实例管理接口集成测试（Pack G P0）。
验证实例 CRUD 完整流程，包括权限校验。
"""
import pytest
from httpx import AsyncClient


async def _get_admin_headers(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/v1/system/init/")
    resp = await client.post("/api/v1/auth/login/", json={
        "username": "admin", "password": "Admin@2024!",
    })
    assert resp.status_code == 200
    data = resp.json()
    if data.get("password_change_required"):
        change_resp = await client.post("/api/v1/auth/password/change-required/", json={
            "password_change_token": data["password_change_token"],
            "new_password": "AdminReset@2026",
        })
        assert change_resp.status_code == 200
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert resp.status_code == 200
        data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


_MYSQL_INSTANCE = {
    "instance_name": "test-mysql-ci",
    "type": "master",
    "db_type": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root123",
    "remark": "CI 测试用实例",
}


class TestInstanceCRUD:

    @pytest.mark.asyncio
    async def test_create_instance_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/instances/", json=_MYSQL_INSTANCE)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_instances_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/instances/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_instance_as_admin(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        resp = await client.post(
            "/api/v1/instances/",
            json=_MYSQL_INSTANCE,
            headers=headers,
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        # Router returns {"status": 0, "data": {...}} wrapper
        data = body.get("data", body)
        assert data["instance_name"] == "test-mysql-ci"
        assert data["db_type"] == "mysql"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_instances_as_admin(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        # 先创建一个
        await client.post("/api/v1/instances/", json=_MYSQL_INSTANCE, headers=headers)
        resp = await client.get("/api/v1/instances/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_instance_by_id(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        create_resp = await client.post(
            "/api/v1/instances/",
            json=_MYSQL_INSTANCE,
            headers=headers,
        )
        assert create_resp.status_code in (200, 201)
        create_body = create_resp.json()
        instance_id = create_body.get("data", create_body)["id"]

        get_resp = await client.get(
            f"/api/v1/instances/{instance_id}/",
            headers=headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == instance_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_instance_returns_404(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        resp = await client.get("/api/v1/instances/99999999/", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_instance_missing_required_fields(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        resp = await client.post(
            "/api/v1/instances/",
            json={"instance_name": "incomplete"},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_instance(self, client: AsyncClient):
        headers = await _get_admin_headers(client)
        create_resp = await client.post(
            "/api/v1/instances/",
            json={**_MYSQL_INSTANCE, "instance_name": "test-delete-ci"},
            headers=headers,
        )
        assert create_resp.status_code in (200, 201)
        create_body = create_resp.json()
        instance_id = create_body.get("data", create_body)["id"]

        del_resp = await client.delete(
            f"/api/v1/instances/{instance_id}/",
            headers=headers,
        )
        assert del_resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_password_not_exposed_in_response(self, client: AsyncClient):
        """实例密码不应在响应体中明文返回。"""
        headers = await _get_admin_headers(client)
        create_resp = await client.post(
            "/api/v1/instances/",
            json={**_MYSQL_INSTANCE, "instance_name": "test-pwd-ci"},
            headers=headers,
        )
        assert create_resp.status_code in (200, 201)
        resp_text = create_resp.text
        assert "root123" not in resp_text  # 密码不应明文出现
