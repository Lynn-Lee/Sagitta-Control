"""
应用配置 — 通过 Pydantic Settings 从环境变量读取，类型安全。
所有配置项均有默认值，便于开发环境零配置启动。

注意：认证（LDAP/CAS）、通知（钉钉/飞书/企微/邮件）、AI 等功能
统一使用 SystemConfig 数据库配置（通过 /api/v1/system/config 管理），
不在此处通过环境变量配置（方便运行时修改，无需重启服务）。
"""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── 应用基础 ─────────────────────────────────────────────
    APP_ENV: Literal["development", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ─── 数据库 ───────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://sagitta:sagitta123@localhost:5432/sagittadb"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://sagitta:sagitta123@localhost:5432/sagittadb"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # ─── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis123@localhost:6379/0"

    # ─── 安全 ─────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── 多租户预留（企业版固定为 1）─────────────────────────
    TENANT_ID: int = 1

    # ─── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:5173", "http://localhost:3000"]

    # ─── 可观测中心 ────────────────────────────────────────────
    PROMETHEUS_URL: str = "http://localhost:9090"
    ALERTMANAGER_URL: str = "http://localhost:9093"
    GRAFANA_URL: str = "http://localhost:3000"

    # ─── goInception（可选增强，用于 MySQL SQL 审核）──────────
    ENABLE_GOINCEPTION: bool = False
    GO_INCEPTION_HOST: str = ""
    GO_INCEPTION_PORT: int = 4000

    # ─── Oracle 驱动模式（11g 需 Thick 模式）──────────────────
    ORACLE_DRIVER_MODE: Literal["auto", "thin", "thick"] = "auto"
    ORACLE_CLIENT_LIB_DIR: str = ""
    ORACLE_CLIENT_CONFIG_DIR: str = ""

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        _default_key = "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS"
        if _default_key == self.SECRET_KEY:
            if self.APP_ENV == "production":
                raise ValueError(
                    "生产环境禁止使用默认 SECRET_KEY，"
                    "请设置环境变量 SECRET_KEY 为至少 32 字符的随机字符串。\n"
                    '生成命令：python -c "import secrets; print(secrets.token_hex(32))"'
                )
            import warnings

            warnings.warn(
                "SECRET_KEY 使用默认值，请在生产环境中替换！",
                stacklevel=2,
            )
        return self

    @property
    def celery_broker_url(self) -> str:
        return self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.REDIS_URL


# 全局单例
settings = Settings()
