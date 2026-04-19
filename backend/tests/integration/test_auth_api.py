"""
认证模块集成测试（Pack G P0）。
使用 ASGITransport + 测试 DB，验证完整 HTTP 请求/响应流程。
"""
import pytest
from httpx import AsyncClient

# ── 辅助：初始化管理员 ────────────────────────────────────────

async def _init_and_login(client: AsyncClient) -> tuple[str, str]:
    """确保 admin 用户存在，并在强制改密后返回 (access_token, refresh_token)。"""
    # 先尝试初始化系统（幂等）
    await client.post("/api/v1/system/init/")
    resp = await client.post("/api/v1/auth/login/", json={
        "username": "admin", "password": "Admin@2024!",
    })
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()
    if data.get("password_change_required"):
        change_resp = await client.post("/api/v1/auth/password/change-required/", json={
            "password_change_token": data["password_change_token"],
            "new_password": "AdminReset@2026",
        })
        assert change_resp.status_code == 200, f"强制改密失败: {change_resp.text}"
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert resp.status_code == 200, f"改密后登录失败: {resp.text}"
        data = resp.json()
    return data["access_token"], data["refresh_token"]


# ── 登录 ─────────────────────────────────────────────────────

class TestLogin:
    @pytest.mark.asyncio
    async def test_default_password_requires_change_before_tokens(self, client: AsyncClient):
        await client.post("/api/v1/system/init/")
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "Admin@2024!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["password_change_required"] is True
        assert data["access_token"] is None
        assert data["refresh_token"] is None
        assert data["password_change_token"]

    @pytest.mark.asyncio
    async def test_valid_credentials_return_tokens(self, client: AsyncClient):
        access, refresh = await _init_and_login(client)
        assert len(access) > 20
        assert len(refresh) > 20

    @pytest.mark.asyncio
    async def test_force_change_password_allows_relogin(self, client: AsyncClient):
        await client.post("/api/v1/system/init/")
        login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "Admin@2024!",
        })
        change_resp = await client.post("/api/v1/auth/password/change-required/", json={
            "password_change_token": login_resp.json()["password_change_token"],
            "new_password": "AdminReset@2026",
        })
        assert change_resp.status_code == 200

        relogin_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert relogin_resp.status_code == 200
        relogin_data = relogin_resp.json()
        assert relogin_data["password_change_required"] is False
        assert relogin_data["access_token"]
        assert relogin_data["refresh_token"]

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(self, client: AsyncClient):
        await client.post("/api/v1/system/init/")
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "ghost_user_xyz", "password": "anything",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_fields_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login/", json={"username": "admin"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_token_response_has_expected_fields(self, client: AsyncClient):
        access, refresh = await _init_and_login(client)
        # access token 验证
        resp = await client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
        me = resp.json()
        assert "username" in me
        assert me["username"] == "admin"
        assert "is_superuser" in me
        assert me["is_superuser"] is True


# ── Token 刷新 ────────────────────────────────────────────────

class TestTokenRefresh:

    @pytest.mark.asyncio
    async def test_valid_refresh_returns_new_tokens(self, client: AsyncClient):
        _, refresh = await _init_and_login(client)
        resp = await client.post("/api/v1/auth/token/refresh/", json={
            "refresh_token": refresh,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/token/refresh/", json={
            "refresh_token": "invalid.token.here",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_as_refresh_returns_401(self, client: AsyncClient):
        access, _ = await _init_and_login(client)
        resp = await client.post("/api/v1/auth/token/refresh/", json={
            "refresh_token": access,  # 故意传 access token
        })
        assert resp.status_code == 401


# ── /me 端点 ──────────────────────────────────────────────────

class TestMe:

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_token_returns_user(self, client: AsyncClient):
        access, _ = await _init_and_login(client)
        resp = await client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert "permissions" in data
        assert "tenant_id" in data

    @pytest.mark.asyncio
    async def test_me_with_malformed_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401


# ── 登出 ─────────────────────────────────────────────────────

class TestLogout:

    @pytest.mark.asyncio
    async def test_logout_returns_ok(self, client: AsyncClient):
        access, _ = await _init_and_login(client)
        resp = await client.post(
            "/api/v1/auth/logout/",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == 0

    @pytest.mark.asyncio
    async def test_logout_without_token_still_ok(self, client: AsyncClient):
        """登出接口即使无 token 也不应 500（无感知处理）。"""
        resp = await client.post("/api/v1/auth/logout/")
        # 401 或 200 均可接受，不应 500
        assert resp.status_code in (200, 401, 403)


# ── 健康检查 ──────────────────────────────────────────────────

class TestHealth:

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
