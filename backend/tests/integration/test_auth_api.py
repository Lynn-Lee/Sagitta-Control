"""
认证模块集成测试（Pack G P0）。
使用 ASGITransport + 测试 DB，验证完整 HTTP 请求/响应流程。
"""
from io import BytesIO

import pytest
from httpx import AsyncClient
from pyotp import TOTP


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


async def _enable_totp(client: AsyncClient) -> str:
    access, _ = await _init_and_login(client)
    setup_resp = await client.post(
        "/api/v1/auth/2fa/setup/",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]
    verify_enable_resp = await client.post(
        "/api/v1/auth/2fa/verify/",
        json={"totp_code": TOTP(secret).now()},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert verify_enable_resp.status_code == 200
    return secret


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
    async def test_force_change_password_rejects_same_password(self, client: AsyncClient):
        await client.post("/api/v1/system/init/")
        login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "Admin@2024!",
        })
        assert login_resp.status_code == 200

        change_resp = await client.post("/api/v1/auth/password/change-required/", json={
            "password_change_token": login_resp.json()["password_change_token"],
            "new_password": "Admin@2024!",
        })
        assert change_resp.status_code == 400
        assert change_resp.json()["detail"] == "新密码不能与当前密码相同"

        relogin_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "Admin@2024!",
        })
        assert relogin_resp.status_code == 200
        assert relogin_resp.json()["password_change_required"] is True

    @pytest.mark.asyncio
    async def test_new_local_user_requires_initial_password_change(self, client: AsyncClient):
        access, _ = await _init_and_login(client)

        create_resp = await client.post(
            "/api/v1/system/users/",
            json={
                "username": "user001",
                "password": "Sagitta@2026A",
                "display_name": "普通用户",
            },
            headers={"Authorization": f"Bearer {access}"},
        )
        assert create_resp.status_code == 200

        login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "user001",
            "password": "Sagitta@2026A",
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["password_change_required"] is True
        assert "当前密码为系统分配的初始密码，首次登录必须先修改密码" in login_data["password_change_reasons"]

    @pytest.mark.asyncio
    async def test_import_existing_user_with_password_resets_and_requires_change(self, client: AsyncClient):
        access, _ = await _init_and_login(client)

        create_resp = await client.post(
            "/api/v1/system/users/",
            json={
                "username": "import_user_1",
                "password": "Origin@2026A",
                "display_name": "导入用户",
            },
            headers={"Authorization": f"Bearer {access}"},
        )
        assert create_resp.status_code == 200

        csv_content = (
            "username,display_name,password\n"
            "import_user_1,导入后用户,Reset@2026B\n"
        ).encode("utf-8")
        import_resp = await client.post(
            "/api/v1/system/users/import/",
            headers={"Authorization": f"Bearer {access}"},
            data={"default_password": "Sagitta@2026A"},
            files={"file": ("users.csv", BytesIO(csv_content), "text/csv")},
        )
        assert import_resp.status_code == 200
        assert import_resp.json()["data"]["updated"] == 1

        old_login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "import_user_1",
            "password": "Origin@2026A",
        })
        assert old_login_resp.status_code == 401

        new_login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "import_user_1",
            "password": "Reset@2026B",
        })
        assert new_login_resp.status_code == 200
        new_login_data = new_login_resp.json()
        assert new_login_data["password_change_required"] is True
        assert "当前密码为系统分配的初始密码，首次登录必须先修改密码" in new_login_data["password_change_reasons"]

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

    @pytest.mark.asyncio
    async def test_totp_enabled_user_requires_second_factor(self, client: AsyncClient):
        await _enable_totp(client)

        login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert data["requires_2fa"] is True
        assert data["two_fa_token"]
        assert data["access_token"] is None
        assert data["refresh_token"] is None

    @pytest.mark.asyncio
    async def test_login_2fa_verify_returns_formal_tokens(self, client: AsyncClient):
        secret = await _enable_totp(client)

        login_resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["requires_2fa"] is True

        verify_login_resp = await client.post("/api/v1/auth/2fa/login/verify/", json={
            "two_fa_token": login_data["two_fa_token"],
            "totp_code": TOTP(secret).now(),
        })
        assert verify_login_resp.status_code == 200
        verify_login_data = verify_login_resp.json()
        assert verify_login_data["access_token"]
        assert verify_login_data["refresh_token"]

        me_resp = await client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {verify_login_data['access_token']}"},
        )
        assert me_resp.status_code == 200


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
