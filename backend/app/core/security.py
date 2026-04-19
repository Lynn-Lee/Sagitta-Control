"""
安全模块：JWT 签发/验证 + 密码哈希 + 字段加密。
直接使用 bcrypt 库，绕过 passlib 1.7.4 的 detect_wrap_bug 兼容性问题。
"""
import base64
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from app.core.config import settings

DEFAULT_PASSWORDS = {"Admin@2024!"}
PASSWORD_EXPIRE_DAYS = 30
PASSWORD_EXPIRY_WARNING_DAYS = 7

# ─── 密码哈希 ─────────────────────────────────────────────────

def _prepare_password(password: str) -> bytes:
    """SHA-256 预处理，输出固定 44 字节，彻底规避 bcrypt 72字节限制。"""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)   # 44 bytes，远低于 72


def hash_password(password: str) -> str:
    """哈希密码，返回字符串存入数据库。"""
    hashed = bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码。"""
    try:
        return bcrypt.checkpw(
            _prepare_password(plain_password),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_policy_violations(password: str) -> list[str]:
    """返回密码复杂度不符合项。空列表表示通过。"""
    violations: list[str] = []
    if len(password) < 8:
        violations.append("密码长度不能少于 8 位")
    if not re.search(r"[A-Z]", password):
        violations.append("密码必须包含至少 1 个大写字母")
    if not re.search(r"[a-z]", password):
        violations.append("密码必须包含至少 1 个小写字母")
    if not re.search(r"\d", password):
        violations.append("密码必须包含至少 1 个数字")
    if not re.search(r"[^A-Za-z0-9]", password):
        violations.append("密码必须包含至少 1 个特殊字符")
    return violations


def validate_password_strength(password: str) -> str:
    violations = get_password_policy_violations(password)
    if violations:
        raise ValueError("；".join(violations))
    return password


def is_password_expired(password_changed_at: datetime | None, now: datetime | None = None) -> bool:
    if password_changed_at is None:
        return True
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return current >= password_changed_at + timedelta(days=PASSWORD_EXPIRE_DAYS)


def get_password_days_until_expiry(
    password_changed_at: datetime | None,
    now: datetime | None = None,
) -> int:
    if password_changed_at is None:
        return 0
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    expires_at = password_changed_at + timedelta(days=PASSWORD_EXPIRE_DAYS)
    remaining_seconds = (expires_at - current).total_seconds()
    if remaining_seconds <= 0:
        return 0
    return int((remaining_seconds + 86399) // 86400)


def is_password_expiring_soon(password_changed_at: datetime | None, now: datetime | None = None) -> bool:
    if is_password_expired(password_changed_at, now):
        return False
    days_until_expiry = get_password_days_until_expiry(password_changed_at, now)
    return days_until_expiry <= PASSWORD_EXPIRY_WARNING_DAYS


def get_login_password_change_reasons(
    password: str,
    password_changed_at: datetime | None = None,
) -> list[str]:
    reasons = get_password_policy_violations(password)
    if password in DEFAULT_PASSWORDS:
        reasons.insert(0, "当前密码为系统默认密码，必须先修改密码")
    if is_password_expired(password_changed_at):
        reasons.append(f"当前密码已超过 {PASSWORD_EXPIRE_DAYS} 天未修改，请先更新密码")
    return reasons


# ─── JWT ──────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload.update({"exp": expire, "type": "access"})
    if "tenant_id" not in payload:
        payload["tenant_id"] = settings.TENANT_ID
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    expire = datetime.now(UTC) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload.update({"exp": expire, "type": "refresh"})
    if "tenant_id" not in payload:
        payload["tenant_id"] = settings.TENANT_ID
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_password_change_token(data: dict[str, Any], expires_minutes: int = 10) -> str:
    payload = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload.update({"exp": expire, "type": "password_change"})
    if "tenant_id" not in payload:
        payload["tenant_id"] = settings.TENANT_ID
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ─── 字段级加密（用于 Instance.password 等敏感字段）──────────

from cryptography.fernet import Fernet  # noqa: E402


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_field(value: str) -> str:
    """加密敏感字段（实例密码、SSH密钥等）。"""
    if not value:
        return value
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    """解密敏感字段，兼容未加密的旧数据。"""
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except Exception:
        return value
