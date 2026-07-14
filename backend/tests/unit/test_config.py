import pytest
from pydantic import ValidationError

from app.core.config import Settings

# 用于生产环境用例的合法字段加密密钥（与 SECRET_KEY 分离）。
VALID_FERNET_KEY = "dhVcBCzIxLepnTAaF1FUvGO-jDBLgjcOBsPDRgZNVdA="
VALID_SECRET_KEY = "r4ndom-secret-key-with-48-safe-chars-2026"


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError, match="生产环境禁止使用占位/默认 SECRET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY="CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS",
            FERNET_KEY=VALID_FERNET_KEY,
        )


def test_production_rejects_helm_default_secret_key():
    """Helm 曾用的另一公开默认串也必须被拒绝（SAG-001）。"""
    with pytest.raises(ValidationError, match="生产环境禁止使用占位/默认 SECRET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY="CHANGE_ME_USE_RANDOM_32_CHARS_IN_PRODUCTION",
            FERNET_KEY=VALID_FERNET_KEY,
        )


def test_production_rejects_short_secret_key():
    with pytest.raises(ValidationError, match="生产环境 SECRET_KEY 长度不足 32 字符"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY="short-secret",
            FERNET_KEY=VALID_FERNET_KEY,
        )


@pytest.mark.parametrize(
    "secret_key",
    [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "01234567890123456789012345678901",
        "password-password-password-password",
        "changeme-changeme-changeme-changeme",
    ],
)
def test_production_rejects_weak_secret_key_patterns(secret_key: str):
    with pytest.raises(ValidationError, match="生产环境 SECRET_KEY 疑似弱密钥"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=secret_key,
            FERNET_KEY=VALID_FERNET_KEY,
        )


def test_production_requires_fernet_key():
    """生产环境必须单独配置 FERNET_KEY（SAG-001）。"""
    with pytest.raises(ValidationError, match="生产环境必须单独配置 FERNET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=VALID_SECRET_KEY,
            AUTH_COOKIE_SECURE=True,
        )


def test_production_rejects_fernet_key_equal_secret_key():
    with pytest.raises(ValidationError, match="FERNET_KEY 不得与 SECRET_KEY 相同"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=VALID_FERNET_KEY,
            FERNET_KEY=VALID_FERNET_KEY,
            AUTH_COOKIE_SECURE=True,
        )


def test_production_rejects_invalid_fernet_key():
    with pytest.raises(ValidationError, match="FERNET_KEY 不是合法的 Fernet 密钥"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=VALID_SECRET_KEY,
            FERNET_KEY="not-a-valid-fernet-key",
            AUTH_COOKIE_SECURE=True,
        )


def test_production_accepts_random_length_secret_key():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=VALID_SECRET_KEY,
        FERNET_KEY=VALID_FERNET_KEY,
        AUTH_COOKIE_SECURE=True,
    )

    assert settings.SECRET_KEY == VALID_SECRET_KEY


def test_production_rejects_insecure_auth_cookie_by_default():
    with pytest.raises(ValidationError, match="生产环境必须设置 AUTH_COOKIE_SECURE=true"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=VALID_SECRET_KEY,
            FERNET_KEY=VALID_FERNET_KEY,
            AUTH_COOKIE_SECURE=False,
        )


def test_production_allows_insecure_auth_cookie_for_explicit_source_test():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=VALID_SECRET_KEY,
        FERNET_KEY=VALID_FERNET_KEY,
        AUTH_COOKIE_SECURE=False,
        ALLOW_INSECURE_AUTH_COOKIE=True,
    )

    assert settings.AUTH_COOKIE_SECURE is False


def test_production_rejects_wildcard_cors_origins():
    with pytest.raises(ValidationError, match="生产环境禁止 CORS_ORIGINS 使用通配符"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY=VALID_SECRET_KEY,
            FERNET_KEY=VALID_FERNET_KEY,
            AUTH_COOKIE_SECURE=True,
            CORS_ORIGINS=["*"],
        )


def test_audit_fail_closed_defaults_by_env():
    """审计 fail-closed：生产默认开启，其它环境默认关闭，可显式覆盖（SAG-014）。"""
    dev = Settings(_env_file=None, APP_ENV="development")
    assert dev.audit_fail_closed is False

    prod = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=VALID_SECRET_KEY,
        FERNET_KEY=VALID_FERNET_KEY,
        AUTH_COOKIE_SECURE=True,
    )
    assert prod.audit_fail_closed is True

    forced_open = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=VALID_SECRET_KEY,
        FERNET_KEY=VALID_FERNET_KEY,
        AUTH_COOKIE_SECURE=True,
        AUDIT_FAIL_CLOSED=False,
    )
    assert forced_open.audit_fail_closed is False
