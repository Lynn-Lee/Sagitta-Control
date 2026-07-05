"""
Sprint 1 认证与用户服务单元测试。
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi import Response
from pydantic import ValidationError

from app.core.security import (
    create_access_token,
    create_password_change_token,
    create_refresh_token,
    decode_token,
    decrypt_field,
    encrypt_field,
    get_login_password_change_reasons,
    get_password_days_until_expiry,
    hash_password,
    is_initial_password_state,
    is_password_expired,
    is_password_expiring_soon,
    validate_password_strength,
    verify_password,
)
from app.routers import auth as auth_router
from app.routers.auth import _oauth_login_code_key, exchange_oauth_login_code
from app.schemas.auth import (
    OAuthExchangeRequest,
    RefreshRequest,
    SmsCodeRequest,
    SmsLoginRequest,
    TwoFAVerifyRequest,
)
from app.schemas.user import UserCreate


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value


class FakeAuthRole:
    name = "engineer"


class FakeAuthUser:
    id = 7
    username = "alice"
    display_name = "Alice"
    email = "alice@example.test"
    is_superuser = False
    is_active = True
    auth_type = "local"
    password_changed_at = datetime.now(UTC)
    created_at = datetime.now(UTC)
    password = hash_password("OldPass@123")
    role = FakeAuthRole()
    role_id = 3
    manager_id = None
    employee_id = "E001"
    department = "研发"
    title = "工程师"
    tenant_id = 1
    totp_enabled = False
    totp_secret: str | None = None


class FakeDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pwd = "MySecret@2024"
        hashed = hash_password(pwd)
        assert hashed != pwd
        assert verify_password(pwd, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_empty_password(self):
        hashed = hash_password("password123")
        assert not verify_password("", hashed)


class TestJWT:
    def test_create_and_decode_access_token(self):
        payload = {"sub": "42", "username": "testuser", "tenant_id": 1}
        token = create_access_token(payload)
        decoded = decode_token(token)
        assert decoded["sub"] == "42"
        assert decoded["username"] == "testuser"
        assert decoded["type"] == "access"
        assert decoded["tenant_id"] == 1

    def test_refresh_token_type(self):
        token = create_refresh_token({"sub": "1", "tenant_id": 1})
        decoded = decode_token(token)
        assert decoded["type"] == "refresh"

    def test_password_change_token_type(self):
        token = create_password_change_token({"sub": "1", "tenant_id": 1})
        decoded = decode_token(token)
        assert decoded["type"] == "password_change"

    def test_invalid_token_raises(self):
        from jwt import PyJWTError as JWTError

        with pytest.raises(JWTError):
            decode_token("not.a.valid.token")

    def test_tenant_id_auto_filled(self):
        """未传 tenant_id 时自动填入配置中的默认值。"""
        token = create_access_token({"sub": "1"})
        decoded = decode_token(token)
        assert "tenant_id" in decoded

    @pytest.mark.asyncio
    async def test_oauth_login_code_exchange_is_one_time(self):
        redis = FakeRedis()
        login_code = "a" * 64
        redis.store[_oauth_login_code_key(login_code)] = json.dumps({
            "sub": "42",
            "username": "oauth_user",
            "tenant_id": 1,
            "provider": "oidc",
        })

        http_response = Response()
        response = await exchange_oauth_login_code(
            OAuthExchangeRequest(login_code=login_code),
            response=http_response,
            redis=redis,
        )
        assert response.access_token
        assert response.refresh_token
        assert "access_token=" in http_response.headers["set-cookie"]

        with pytest.raises(HTTPException) as exc:
            await exchange_oauth_login_code(
                OAuthExchangeRequest(login_code=login_code),
                response=Response(),
                redis=redis,
            )
        assert exc.value.status_code == 401


class TestAuthRouterFlows:
    def test_issue_login_response_sets_tokens_and_auth_cookies(self):
        user = FakeAuthUser()
        response = Response()

        tokens = auth_router._issue_login_response(response, user)

        assert tokens.access_token
        assert tokens.refresh_token
        assert decode_token(tokens.access_token)["sub"] == str(user.id)
        assert "access_token=" in response.headers["set-cookie"]

    @pytest.mark.asyncio
    async def test_logout_blacklists_access_token_and_clears_cookies(self):
        token = create_access_token({"sub": "7", "username": "alice", "tenant_id": 1})
        redis = FakeRedis()
        response = Response()

        result = await auth_router.logout(
            request=object(),  # type: ignore[arg-type]
            response=response,
            token=token,
            redis=redis,
        )

        assert result == {"status": 0, "msg": "已退出登录"}
        assert redis.setex_calls
        assert redis.setex_calls[0][0] == f"blacklist:{token}"
        cookie_headers = [
            value.decode()
            for key, value in response.raw_headers
            if key.decode().lower() == "set-cookie"
        ]
        assert len(cookie_headers) >= 2
        assert all("Max-Age=0" in header for header in cookie_headers)

    @pytest.mark.asyncio
    async def test_totp_setup_verify_and_disable_flow(self, monkeypatch):
        import pyotp

        secret = "JBSWY3DPEHPK3PXP"
        db_user = FakeAuthUser()
        db = FakeDB()

        async def get_by_id(db_arg, user_id):
            assert db_arg is db
            assert user_id == db_user.id
            return db_user

        monkeypatch.setattr(auth_router.UserService, "get_by_id", get_by_id)
        monkeypatch.setattr("pyotp.random_base32", lambda: secret)

        setup = await auth_router.setup_2fa({"id": db_user.id}, db)  # type: ignore[arg-type]
        assert setup["secret"] == secret
        assert decrypt_field(db_user.totp_secret) == secret

        code = pyotp.TOTP(secret).now()
        verify_result = await auth_router.verify_2fa(
            TwoFAVerifyRequest(totp_code=code),
            {"id": db_user.id},
            db,  # type: ignore[arg-type]
        )
        assert verify_result == {"status": 0, "msg": "2FA 已启用"}
        assert db_user.totp_enabled is True

        disable_result = await auth_router.disable_2fa(
            TwoFAVerifyRequest(totp_code=code),
            {"id": db_user.id},
            db,  # type: ignore[arg-type]
        )
        assert disable_result == {"status": 0, "msg": "2FA 已禁用"}
        assert db_user.totp_enabled is False
        assert db_user.totp_secret is None
        assert db.commits == 3

    @pytest.mark.asyncio
    async def test_refresh_token_issues_new_cookie_tokens(self, monkeypatch):
        db_user = FakeAuthUser()

        async def get_by_id(db_arg, user_id):
            assert user_id == db_user.id
            return db_user

        monkeypatch.setattr(auth_router.UserService, "get_by_id", get_by_id)
        refresh = create_refresh_token({"sub": str(db_user.id), "tenant_id": db_user.tenant_id})
        response = Response()

        result = await auth_router.refresh_token(
            RefreshRequest(refresh_token=refresh),
            request=object(),  # type: ignore[arg-type]
            response=response,
            db=object(),  # type: ignore[arg-type]
        )

        assert result.access_token
        assert result.refresh_token
        assert "access_token=" in response.headers["set-cookie"]

    @pytest.mark.asyncio
    async def test_sms_send_code_delegates_to_service(self, monkeypatch):
        import app.services.sms_auth as sms_auth_module

        async def send_sms_code(db_arg, phone):
            assert phone == "13800000000"
            return {"success": True, "message": "ok"}

        monkeypatch.setattr(sms_auth_module, "send_sms_code", send_sms_code)

        result = await auth_router.sms_send_code(
            SmsCodeRequest(phone="13800000000"),
            db=object(),  # type: ignore[arg-type]
        )

        assert result == {"success": True, "message": "ok"}

    @pytest.mark.asyncio
    async def test_sms_login_issues_tokens_after_code_verification(self, monkeypatch):
        import app.services.sms_auth as sms_auth_module

        db_user = FakeAuthUser()

        async def verify_sms_code(phone, code):
            assert (phone, code) == ("13800000000", "123456")
            return True

        async def get_by_phone(db_arg, phone):
            assert phone == "13800000000"
            return db_user

        monkeypatch.setattr(sms_auth_module, "verify_sms_code", verify_sms_code)
        monkeypatch.setattr(auth_router.UserService, "get_by_phone", get_by_phone)
        response = Response()

        result = await auth_router.sms_login(
            SmsLoginRequest(phone="13800000000", code="123456"),
            response=response,
            db=object(),  # type: ignore[arg-type]
        )

        assert result.access_token
        assert result.refresh_token
        assert "access_token=" in response.headers["set-cookie"]


class TestFieldEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "my_database_password_123!"
        encrypted = encrypt_field(original)
        assert encrypted != original
        assert decrypt_field(encrypted) == original

    def test_empty_string_passthrough(self):
        assert encrypt_field("") == ""
        assert decrypt_field("") == ""

    def test_different_values_different_ciphertext(self):
        e1 = encrypt_field("password1")
        e2 = encrypt_field("password2")
        assert e1 != e2

    def test_decrypt_unencrypted_returns_original(self):
        """兼容旧数据：解密未加密的明文时原样返回。"""
        plain = "old_plain_password"
        result = decrypt_field(plain)
        assert result == plain


class TestUserCreateSchema:
    def test_valid_user(self):
        u = UserCreate(username="jiali", password="SecurePass@1")
        assert u.username == "jiali"

    def test_short_username_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(username="a", password="Password@123")

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(username="validuser", password="short")

    def test_invalid_username_chars(self):
        with pytest.raises(ValidationError):
            UserCreate(username="user name!", password="Password@123")


class TestPasswordPolicy:
    def test_validate_password_strength_accepts_required_format(self):
        assert validate_password_strength("Password@123") == "Password@123"

    def test_validate_password_strength_rejects_missing_uppercase(self):
        with pytest.raises(ValueError):
            validate_password_strength("password123")

    def test_validate_password_strength_rejects_missing_number(self):
        with pytest.raises(ValueError):
            validate_password_strength("PasswordOnly")

    def test_validate_password_strength_rejects_missing_special_char(self):
        with pytest.raises(ValueError):
            validate_password_strength("Password123")

    def test_default_password_requires_change(self):
        reasons = get_login_password_change_reasons("Admin@2024!")
        assert "当前密码为系统默认密码，必须先修改密码" in reasons

    def test_initial_password_requires_change(self):
        now = datetime.now(UTC)
        reasons = get_login_password_change_reasons(
            "Sagitta@2026A",
            now,
            force_change_on_first_login=True,
        )
        assert "当前密码为系统分配的初始密码，首次登录必须先修改密码" in reasons

    def test_initial_password_state_detects_new_user(self):
        now = datetime.now(UTC)
        assert is_initial_password_state(now, now) is True

    def test_initial_password_state_ignores_changed_password(self):
        created_at = datetime.now(UTC) - timedelta(days=1)
        changed_at = datetime.now(UTC)
        assert is_initial_password_state(changed_at, created_at) is False

    def test_password_expired_after_30_days(self):
        changed_at = datetime.now(UTC) - timedelta(days=31)
        assert is_password_expired(changed_at) is True

    def test_password_not_expired_within_30_days(self):
        changed_at = datetime.now(UTC) - timedelta(days=29)
        assert is_password_expired(changed_at) is False

    def test_password_expiring_soon_within_7_days(self):
        changed_at = datetime.now(UTC) - timedelta(days=24)
        assert is_password_expiring_soon(changed_at) is True

    def test_password_not_expiring_soon_before_warning_window(self):
        changed_at = datetime.now(UTC) - timedelta(days=20)
        assert is_password_expiring_soon(changed_at) is False

    def test_password_days_until_expiry_rounds_up_partial_days(self):
        changed_at = datetime.now(UTC) - timedelta(days=29, hours=12)
        assert get_password_days_until_expiry(changed_at) == 1

    def test_expired_password_requires_change(self):
        reasons = get_login_password_change_reasons(
            "Password@123",
            datetime.now(UTC) - timedelta(days=31),
        )
        assert "当前密码已超过 30 天未修改，请先更新密码" in reasons
