"""商业版启动完整性校验。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import settings

logger = logging.getLogger(__name__)


class IntegrityError(RuntimeError):
    """Manifest 签名或文件摘要校验失败。"""


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _load_public_key() -> Ed25519PublicKey:
    key = (settings.MANIFEST_PUBLIC_KEY or settings.LICENSE_PUBLIC_KEY).strip()
    if not key:
        raise IntegrityError("未配置 Manifest 验签公钥")
    if "BEGIN PUBLIC KEY" in key:
        loaded = serialization.load_pem_public_key(key.encode())
        if not isinstance(loaded, Ed25519PublicKey):
            raise IntegrityError("Manifest 公钥类型无效")
        return loaded
    return Ed25519PublicKey.from_public_bytes(_b64decode(key))


def _safe_manifest_path(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/"):
        raise IntegrityError(f"Manifest 文件路径非法：{relative_path}")
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise IntegrityError(f"Manifest 文件路径越界：{relative_path}") from exc
    return path


def verify_startup_integrity() -> None:
    """验证商业镜像内关键文件未被替换。

    开发环境默认不强制；商业镜像设置 APP_INTEGRITY_REQUIRED=true 后，
    启动时必须存在签名 Manifest，且 Manifest 内列出的文件摘要全部匹配。
    """

    manifest_path = Path(settings.APP_INTEGRITY_MANIFEST)
    if not manifest_path.exists():
        if settings.APP_INTEGRITY_REQUIRED:
            raise IntegrityError(f"完整性 Manifest 不存在：{manifest_path}")
        logger.info("integrity_manifest_missing_skip path=%s", manifest_path)
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError("完整性 Manifest 读取失败") from exc

    payload = manifest.get("payload")
    signature = manifest.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
        raise IntegrityError("完整性 Manifest 必须包含 payload 和 signature")

    public_key = _load_public_key()
    try:
        public_key.verify(_b64decode(signature), _canonical_payload(payload))
    except (InvalidSignature, ValueError) as exc:
        raise IntegrityError("完整性 Manifest 签名无效") from exc

    root = Path(settings.APP_INTEGRITY_ROOT).resolve()
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise IntegrityError("完整性 Manifest 未包含文件清单")

    for item in files:
        if not isinstance(item, dict):
            raise IntegrityError("完整性 Manifest 文件项格式无效")
        relative_path = str(item.get("path") or "")
        expected_sha256 = str(item.get("sha256") or "").lower()
        if len(expected_sha256) != 64:
            raise IntegrityError(f"Manifest 文件摘要无效：{relative_path}")
        path = _safe_manifest_path(root, relative_path)
        if not path.is_file():
            raise IntegrityError(f"Manifest 文件不存在：{relative_path}")
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise IntegrityError(f"Manifest 文件摘要不匹配：{relative_path}")

    logger.info("startup_integrity_verified files=%s manifest=%s", len(files), manifest_path)
