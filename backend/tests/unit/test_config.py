import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError, match="生产环境禁止使用默认 SECRET_KEY"):
        Settings(_env_file=None, APP_ENV="production")


def test_production_rejects_short_secret_key():
    with pytest.raises(ValidationError, match="生产环境 SECRET_KEY 长度不足 32 字符"):
        Settings(_env_file=None, APP_ENV="production", SECRET_KEY="short-secret")


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
        Settings(_env_file=None, APP_ENV="production", SECRET_KEY=secret_key)


def test_production_accepts_random_length_secret_key():
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY="r4ndom-secret-key-with-48-safe-chars-2026",
    )

    assert settings.SECRET_KEY == "r4ndom-secret-key-with-48-safe-chars-2026"
