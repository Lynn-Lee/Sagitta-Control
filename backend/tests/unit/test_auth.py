"""
Sprint 1 认证与用户服务单元测试。
"""

from datetime import UTC, datetime, timedelta

import pytest
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
    is_password_expiring_soon,
    is_password_expired,
    validate_password_strength,
    verify_password,
)
from app.schemas.user import UserCreate


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
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_token("not.a.valid.token")

    def test_tenant_id_auto_filled(self):
        """未传 tenant_id 时自动填入配置中的默认值。"""
        token = create_access_token({"sub": "1"})
        decoded = decode_token(token)
        assert "tenant_id" in decoded


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
