"""
应用配置 — 通过 Pydantic Settings 从环境变量读取，类型安全。
所有配置项均有默认值，便于开发环境零配置启动。

注意：认证（LDAP/CAS/OIDC）、通知（钉钉/飞书/企微/邮件）、AI 等功能
统一使用 SystemConfig 数据库配置（通过 /api/v1/system/config 管理）。
AI_* 环境变量仅作为首次初始化 SystemConfig 时的部署默认值，运行时修改仍以数据库配置为准。
"""

import re
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 已知占位/默认密钥：任何部署渠道（后端默认、Helm values 等）曾使用过的公开串。
_KNOWN_DEFAULT_SECRETS = {
    "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS",
    "CHANGE_ME_USE_RANDOM_32_CHARS_IN_PRODUCTION",
    "CHANGE_ME_GENERATE_WITH_cryptography_fernet",
}
# 弱密钥模式：占位串/常见弱口令在任意位置出现即判定为弱（不再只匹配前缀）。
_WEAK_SECRET_PATTERNS = re.compile(
    r"^(.)\1*$"  # 全部相同字符
    r"|(0123456789|abcdefgh|password|change[_-]?me|changeme|placeholder|your[_-]?secret)",
    re.IGNORECASE,
)


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
    DATABASE_URL: str = "postgresql+asyncpg://sagitta:sagitta123@localhost:5432/sagitta_control"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://sagitta:sagitta123@localhost:5432/sagitta_control"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # ─── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis123@localhost:6379/0"

    # ─── 安全 ─────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS"
    # 字段级加密（实例密码/SSH 私钥/TOTP 密钥）专用密钥，与 JWT 签名的 SECRET_KEY 分离。
    # 生成命令：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # 留空时回退为从 SECRET_KEY 派生（仅兼容旧部署，生产环境强制要求单独配置）。
    FERNET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False
    ALLOW_INSECURE_AUTH_COOKIE: bool = False
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "strict"
    AUTH_COOKIE_DOMAIN: str = ""
    # 应用前置的可信反向代理层数，用于从 X-Forwarded-For 还原真实客户端 IP。
    # 标准部署为单层 nginx，故默认 1；直连无代理时设为 0（此时忽略 XFF，只信任 socket 对端）。
    # 该机制假定 backend 仅经可信代理可达（内网隔离），否则需配合网络隔离防止 XFF 伪造。
    TRUSTED_PROXY_COUNT: int = 1

    # ─── 正式授权 ─────────────────────────────────────────────
    LICENSE_PUBLIC_KEY: str = "3Jz3SK-mTWZwGy6VX8gUBUWJ-kisvGnO3c_x18Fk_Ms"
    LICENSE_CUSTOMER_ID: str = ""
    LICENSE_SERVER_URL: str = "https://license.loveai.asia"
    LICENSE_SERVER_TOKEN: str = ""
    LICENSE_AUTO_REFRESH_ENABLED: bool = True
    LICENSE_ONLINE_GRACE_DAYS: int = 7
    LICENSE_RENEWAL_NOTIFY_DAYS: str = "30,21,14,7,1"
    LICENSE_DEPLOYMENT_ID: str = ""
    # 内网离线签发要把 Challenge 带出网再带回，60 分钟不够用，默认给一天。
    LICENSE_OFFLINE_CHALLENGE_TTL_MINUTES: int = 1440
    LICENSE_ALLOW_LEGACY_LICENSE_IMPORT: bool = False

    # ─── 用户部署版完整性校验 ─────────────────────────────────────
    APP_INTEGRITY_REQUIRED: bool = False
    APP_INTEGRITY_MANIFEST: str = "/app/COMMERCIAL-MANIFEST.json"
    APP_INTEGRITY_ROOT: str = "/app"
    MANIFEST_PUBLIC_KEY: str = ""
    SAGITTA_CONTROL_COMMERCIAL_BUILD: bool = False

    # ─── 多租户预留（企业版固定为 1）─────────────────────────
    TENANT_ID: int = 1

    # ─── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:5173", "http://localhost:3000"]

    # ─── 审计 ─────────────────────────────────────────────────
    # 审计日志写入失败时是否阻断业务（fail-closed）。
    # None：按环境自动——生产环境 fail-closed，其它环境 fail-open；显式 true/false 可强制覆盖。
    AUDIT_FAIL_CLOSED: bool | None = None

    # ─── 观测中心 ────────────────────────────────────────────
    PROMETHEUS_URL: str = "http://localhost:9090"
    ALERTMANAGER_URL: str = "http://localhost:9093"
    GRAFANA_URL: str = "http://localhost:3000"

    # ─── AI 首次初始化默认值（写入 SystemConfig 后以数据库为准）──────────
    AI_ENABLED: str = ""
    AI_PROVIDER: str = ""
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""

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
        is_default = self.SECRET_KEY in _KNOWN_DEFAULT_SECRETS
        if self.APP_ENV == "production":
            if is_default:
                raise ValueError(
                    "生产环境禁止使用占位/默认 SECRET_KEY，"
                    "请设置环境变量 SECRET_KEY 为至少 32 字符的随机字符串。\n"
                    '生成命令：python -c "import secrets; print(secrets.token_hex(32))"'
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError("生产环境 SECRET_KEY 长度不足 32 字符。")
            if _WEAK_SECRET_PATTERNS.search(self.SECRET_KEY):
                raise ValueError("生产环境 SECRET_KEY 疑似弱密钥（重复字符/占位串/常见弱口令），请更换为随机字符串。")

            # 字段加密密钥必须与 SECRET_KEY 分离，且为合法 Fernet 密钥。
            if not self.FERNET_KEY or self.FERNET_KEY in _KNOWN_DEFAULT_SECRETS:
                raise ValueError(
                    "生产环境必须单独配置 FERNET_KEY（不得留空或使用占位值）。\n"
                    '生成命令：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
            if self.FERNET_KEY == self.SECRET_KEY:
                raise ValueError("FERNET_KEY 不得与 SECRET_KEY 相同，字段加密密钥必须与签名密钥分离。")
            from cryptography.fernet import Fernet

            try:
                Fernet(self.FERNET_KEY.encode())
            except Exception as exc:
                raise ValueError(
                    "FERNET_KEY 不是合法的 Fernet 密钥（需为 base64 编码的 32 字节密钥）。"
                ) from exc
        elif is_default:
            import warnings

            warnings.warn(
                "SECRET_KEY 使用默认值，请在生产环境中替换！",
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def validate_cors_origins(self) -> "Settings":
        if self.APP_ENV == "production" and "*" in self.CORS_ORIGINS:
            raise ValueError("生产环境禁止 CORS_ORIGINS 使用通配符 '*'。")
        return self

    @model_validator(mode="after")
    def validate_cookie_security(self) -> "Settings":
        if (
            self.APP_ENV == "production"
            and not self.AUTH_COOKIE_SECURE
            and not self.ALLOW_INSECURE_AUTH_COOKIE
        ):
            raise ValueError("生产环境必须设置 AUTH_COOKIE_SECURE=true；仅源码 HTTP 测试环境可显式开启豁免。")
        return self

    @property
    def audit_fail_closed(self) -> bool:
        """审计写入失败是否阻断业务：显式配置优先，否则生产环境默认阻断。"""
        if self.AUDIT_FAIL_CLOSED is not None:
            return self.AUDIT_FAIL_CLOSED
        return self.APP_ENV == "production"

    @property
    def celery_broker_url(self) -> str:
        return self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.REDIS_URL


# 全局单例
settings = Settings()
