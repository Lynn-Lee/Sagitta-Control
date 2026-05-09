"""企业 License 验签与访问控制。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException
from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.instance import Instance
from app.models.system import LicenseRecord
from app.models.user import Users

LICENSE_FEATURES = {"workflow", "query", "archive", "monitor", "ai", "masking", "instance"}
LICENSE_PROJECT_CODE = "sagittadb"
LICENSE_PROJECT_NAME = "SagittaDB"
TRIAL_FEATURES = sorted(LICENSE_FEATURES)
LICENSE_PROTECTED_FEATURE_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("/api/v1/workflow", "workflow"),
    ("/api/v1/query", "query"),
    ("/api/v1/archive", "archive"),
    ("/api/v1/monitor", "monitor"),
    ("/api/v1/ai", "ai"),
    ("/api/v1/masking", "masking"),
    ("/api/v1/workflow-templates", "workflow"),
    ("/api/v1/instances", "instance"),
)
LICENSE_PROTECTED_SYSTEM_PREFIXES = (
    "/api/v1/system/config",
    "/api/v1/system/users",
    "/api/v1/system/groups",
    "/api/v1/system/roles",
    "/api/v1/system/user-groups",
    "/api/v1/system/resource-groups",
    "/api/v1/system/approval-flows",
)
LICENSE_EXEMPT_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/system/license",
    "/health",
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
)


@dataclass(slots=True)
class LicenseCheck:
    allowed: bool
    status: str
    reason: str = ""
    feature: str = ""


class LicenseService:
    """验证签名 License 文件，并推导运行时访问决策。"""

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def _canonical_payload(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode())

    @staticmethod
    def _load_public_key() -> Ed25519PublicKey:
        key = settings.LICENSE_PUBLIC_KEY.strip()
        if not key:
            raise HTTPException(status_code=400, detail="未配置 License 公钥")
        if "BEGIN PUBLIC KEY" in key:
            from cryptography.hazmat.primitives import serialization

            loaded = serialization.load_pem_public_key(key.encode())
            if not isinstance(loaded, Ed25519PublicKey):
                raise HTTPException(status_code=400, detail="License 公钥类型无效")
            return loaded
        raw = LicenseService._b64decode(key)
        return Ed25519PublicKey.from_public_bytes(raw)

    @staticmethod
    def _parse_license_document(raw_license: str | dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        if isinstance(raw_license, str):
            try:
                doc = json.loads(raw_license)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="License JSON 格式无效") from exc
        else:
            doc = raw_license
        if not isinstance(doc, dict):
            raise HTTPException(status_code=400, detail="License 必须是 JSON 对象")
        payload = doc.get("payload")
        signature = doc.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
            raise HTTPException(status_code=400, detail="License 必须包含 payload 和 signature")
        normalized_raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return payload, signature, normalized_raw

    @staticmethod
    def _validate_payload_shape(payload: dict[str, Any]) -> None:
        required = {
            "license_id",
            "customer_id",
            "company_name",
            "edition",
            "not_before",
            "expires_at",
            "features",
            "limits",
            "issued_at",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise HTTPException(status_code=400, detail=f"License 缺少字段：{', '.join(missing)}")
        if not isinstance(payload.get("features"), list):
            raise HTTPException(status_code=400, detail="License features 必须是数组")
        if not isinstance(payload.get("limits"), dict):
            raise HTTPException(status_code=400, detail="License limits 必须是对象")

    @staticmethod
    def _validate_customer(payload: dict[str, Any]) -> None:
        expected = settings.LICENSE_CUSTOMER_ID.strip()
        if expected and payload.get("customer_id") != expected:
            raise HTTPException(status_code=400, detail="License 客户标识不匹配")

    @staticmethod
    def _validate_project(payload: dict[str, Any]) -> None:
        project = str(payload.get("project") or payload.get("product") or "").strip().lower()
        if project and project != LICENSE_PROJECT_CODE:
            raise HTTPException(status_code=400, detail="License 授权项目不匹配")

    @staticmethod
    def _license_server_url() -> str:
        url = settings.LICENSE_SERVER_URL.strip().rstrip("/")
        if not url:
            raise HTTPException(status_code=501, detail="暂未配置授权服务器")
        return url

    @staticmethod
    def _license_server_headers() -> dict[str, str]:
        token = settings.LICENSE_SERVER_TOKEN.strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    @staticmethod
    def deployment_fingerprint(customer_id: str = "") -> str:
        deployment_id = settings.LICENSE_DEPLOYMENT_ID.strip() or settings.SECRET_KEY.strip()
        customer = customer_id or settings.LICENSE_CUSTOMER_ID.strip() or "trial"
        material = f"sagittadb:{customer}:{deployment_id}".encode()
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _license_server_project_payload() -> dict[str, str]:
        return {"project": LICENSE_PROJECT_CODE, "product": LICENSE_PROJECT_CODE}

    @staticmethod
    def _challenge_secret() -> bytes:
        secret = settings.SECRET_KEY.strip()
        if not secret:
            raise HTTPException(status_code=500, detail="未配置离线授权 Challenge 密钥")
        return secret.encode()

    @staticmethod
    def _sign_challenge_payload(payload: dict[str, Any]) -> str:
        # Challenge 只用于证明当前部署生成过本次离线授权请求；
        # 正式授权仍必须由 Ed25519 License 签名和部署指纹共同约束。
        signature = hmac.new(
            LicenseService._challenge_secret(),
            LicenseService._canonical_payload(payload),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    @staticmethod
    def create_offline_challenge(customer_id: str = "") -> dict[str, Any]:
        customer = customer_id.strip() or settings.LICENSE_CUSTOMER_ID.strip()
        if not customer:
            raise HTTPException(status_code=400, detail="请输入客户标识")
        now = LicenseService._utcnow()
        expires_at = now + timedelta(minutes=settings.LICENSE_OFFLINE_CHALLENGE_TTL_MINUTES)
        payload = {
            "project": LICENSE_PROJECT_CODE,
            "product": LICENSE_PROJECT_CODE,
            "customer_id": customer,
            "deployment_fingerprint": LicenseService.deployment_fingerprint(customer),
            "nonce": secrets.token_urlsafe(24),
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        return {
            "payload": payload,
            "signature": LicenseService._sign_challenge_payload(payload),
        }

    @staticmethod
    def verify_offline_challenge(challenge: dict[str, Any]) -> dict[str, Any]:
        payload = challenge.get("payload") if isinstance(challenge, dict) else None
        signature = challenge.get("signature") if isinstance(challenge, dict) else ""
        if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
            raise HTTPException(status_code=400, detail="离线 Challenge 格式无效")
        expected = LicenseService._sign_challenge_payload(payload)
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=400, detail="离线 Challenge 签名无效")
        LicenseService._validate_project(payload)
        customer_id = str(payload.get("customer_id") or "").strip()
        if not customer_id:
            raise HTTPException(status_code=400, detail="离线 Challenge 缺少客户标识")
        expires_at = LicenseService._parse_datetime(str(payload.get("expires_at") or ""))
        if expires_at and LicenseService._utcnow() > expires_at:
            raise HTTPException(status_code=400, detail="离线 Challenge 已过期")
        expected_fingerprint = LicenseService.deployment_fingerprint(customer_id)
        if str(payload.get("deployment_fingerprint") or "") != expected_fingerprint:
            raise HTTPException(status_code=400, detail="离线 Challenge 部署指纹不匹配")
        return payload

    @staticmethod
    def _normalize_import_document(raw_license: str | dict[str, Any]) -> tuple[str | dict[str, Any], dict[str, Any] | None]:
        """兼容旧导入格式，并识别商业版 challenge-response 响应文件。"""
        if isinstance(raw_license, str):
            try:
                doc = json.loads(raw_license)
            except json.JSONDecodeError:
                return raw_license, None
        else:
            doc = raw_license
        if not isinstance(doc, dict) or "challenge" not in doc or "license" not in doc:
            return raw_license, None
        challenge_payload = LicenseService.verify_offline_challenge(doc["challenge"])
        license_doc = doc["license"]
        payload, _, _ = LicenseService.verify_license_document(license_doc)
        customer_id = str(challenge_payload.get("customer_id") or "")
        if payload.get("customer_id") != customer_id:
            raise HTTPException(status_code=400, detail="离线 License 客户标识与 Challenge 不匹配")
        fingerprint = str(challenge_payload.get("deployment_fingerprint") or "")
        if str(payload.get("deployment_fingerprint") or "") != fingerprint:
            raise HTTPException(status_code=400, detail="离线 License 未绑定当前 Challenge 部署指纹")
        return license_doc, challenge_payload

    @staticmethod
    async def _call_license_server(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = LicenseService._license_server_url() + path
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=LicenseService._license_server_headers(),
                )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"授权服务器不可用：{exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="授权服务器返回格式无效") from exc
        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else ""
            raise HTTPException(status_code=response.status_code, detail=detail or "授权服务器拒绝请求")
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="授权服务器返回格式无效")
        return data

    @staticmethod
    def verify_license_document(raw_license: str | dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        payload, signature, normalized_raw = LicenseService._parse_license_document(raw_license)
        LicenseService._validate_payload_shape(payload)
        LicenseService._validate_customer(payload)
        LicenseService._validate_project(payload)
        public_key = LicenseService._load_public_key()
        try:
            public_key.verify(
                LicenseService._b64decode(signature),
                LicenseService._canonical_payload(payload),
            )
        except (InvalidSignature, ValueError) as exc:
            raise HTTPException(status_code=400, detail="License 签名无效") from exc
        expected_fingerprint = str(payload.get("deployment_fingerprint") or "").strip()
        if expected_fingerprint:
            actual_fingerprint = LicenseService.deployment_fingerprint(str(payload.get("customer_id") or ""))
            if expected_fingerprint != actual_fingerprint:
                raise HTTPException(status_code=400, detail="License 部署指纹不匹配")
        return payload, signature, normalized_raw

    @staticmethod
    async def _current_record(db: AsyncSession) -> LicenseRecord | None:
        result = await db.execute(
            select(LicenseRecord)
            .where(LicenseRecord.is_current.is_(True))
            .order_by(LicenseRecord.created_at.desc(), LicenseRecord.id.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def ensure_trial(db: AsyncSession) -> LicenseRecord:
        current = await LicenseService._current_record(db)
        if current:
            return current
        now = LicenseService._utcnow()
        trial = LicenseRecord(
            source="trial",
            status="trial",
            is_current=True,
            license_id="trial",
            customer_id=settings.LICENSE_CUSTOMER_ID or "trial",
            company_name="试用版",
            edition="trial",
            features=TRIAL_FEATURES,
            limits={},
            issued_at=now,
            not_before=now,
            expires_at=now + timedelta(days=settings.LICENSE_TRIAL_DAYS),
            last_check_status="ok",
            last_check_reason="试用期内",
        )
        db.add(trial)
        await db.commit()
        await db.refresh(trial)
        return trial

    @staticmethod
    def evaluate_record(record: LicenseRecord) -> tuple[str, str]:
        now = LicenseService._utcnow()
        not_before = record.not_before
        expires_at = record.expires_at
        if not_before and not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=UTC)
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if not_before and now < not_before:
            return "invalid", "License 尚未生效"
        if expires_at and now > expires_at:
            return "expired", "License 已过期"
        if record.status == "invalid":
            return "invalid", record.last_check_reason or "License 无效"
        return ("trial", "试用期内") if record.source == "trial" else ("licensed", "License 有效")

    @staticmethod
    async def status(db: AsyncSession) -> dict[str, Any]:
        record = await LicenseService.ensure_trial(db)
        status, reason = LicenseService.evaluate_record(record)
        now = LicenseService._utcnow()
        configured_customer_id = settings.LICENSE_CUSTOMER_ID.strip()
        activation_customer_id = configured_customer_id or record.customer_id
        fingerprint_customer_id = activation_customer_id if record.source == "trial" else record.customer_id
        days_remaining: int | None = None
        if record.expires_at:
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            seconds = (expires_at - now).total_seconds()
            days_remaining = max(0, int((seconds + 86399) // 86400))
        if record.last_check_status != status or record.last_check_reason != reason:
            record.last_check_status = status
            record.last_check_reason = reason
            await db.commit()
        warning_level = ""
        if status in {"trial", "licensed"} and days_remaining is not None:
            if days_remaining <= 7:
                warning_level = "critical"
            elif days_remaining <= 30:
                warning_level = "warning"
        return {
            "status": status,
            "reason": reason,
            "source": record.source,
            "is_trial": record.source == "trial",
            "project_code": LICENSE_PROJECT_CODE,
            "project_name": LICENSE_PROJECT_NAME,
            "license_id": record.license_id,
            "customer_id": record.customer_id,
            "activation_customer_id": activation_customer_id,
            "configured_customer_id": configured_customer_id,
            "company_name": record.company_name,
            "edition": record.edition,
            "features": record.features or [],
            "limits": record.limits or {},
            "activation_id": record.activation_id,
            "remote_status": record.remote_status,
            "deployment_fingerprint": record.deployment_fingerprint
            or LicenseService.deployment_fingerprint(fingerprint_customer_id),
            "activation_deployment_fingerprint": LicenseService.deployment_fingerprint(activation_customer_id),
            "last_online_check_at": record.last_online_check_at.isoformat() if record.last_online_check_at else None,
            "issued_at": record.issued_at.isoformat() if record.issued_at else None,
            "not_before": record.not_before.isoformat() if record.not_before else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "days_remaining": days_remaining,
            "needs_renewal": warning_level != "",
            "warning_level": warning_level,
        }

    @staticmethod
    async def _store_license(
        db: AsyncSession,
        raw_license: str | dict[str, Any],
        *,
        source: str,
        activation_code: str = "",
        activation_id: str = "",
        remote_status: str = "",
        server_url: str = "",
        challenge_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload, signature, normalized_raw = LicenseService.verify_license_document(raw_license)
        await db.execute(update(LicenseRecord).values(is_current=False))
        record = LicenseRecord(
            source=source,
            status="licensed",
            is_current=True,
            raw_license=normalized_raw,
            payload=payload,
            signature=signature,
            license_id=str(payload.get("license_id", "")),
            customer_id=str(payload.get("customer_id", "")),
            company_name=str(payload.get("company_name", "")),
            edition=str(payload.get("edition", "enterprise")),
            features=list(payload.get("features") or []),
            limits=dict(payload.get("limits") or {}),
            activation_code=activation_code,
            activation_id=activation_id,
            server_url=server_url,
            remote_status=remote_status,
            deployment_fingerprint=str(payload.get("deployment_fingerprint") or "").strip()
            or LicenseService.deployment_fingerprint(str(payload.get("customer_id") or "")),
            issued_at=LicenseService._parse_datetime(payload.get("issued_at")),
            not_before=LicenseService._parse_datetime(payload.get("not_before")),
            expires_at=LicenseService._parse_datetime(payload.get("expires_at")),
            last_online_check_at=LicenseService._utcnow() if source == "online" else None,
            last_check_status="ok",
            last_check_reason="License 已通过离线 Challenge 导入" if challenge_payload else "License 已导入",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        status, reason = LicenseService.evaluate_record(record)
        if status != "licensed":
            record.status = status
            record.last_check_status = status
            record.last_check_reason = reason
            await db.commit()
        return await LicenseService.status(db)

    @staticmethod
    async def import_license(db: AsyncSession, raw_license: str | dict[str, Any]) -> dict[str, Any]:
        license_doc, challenge_payload = LicenseService._normalize_import_document(raw_license)
        if (
            not challenge_payload
            and settings.APP_ENV == "production"
            and not settings.LICENSE_ALLOW_LEGACY_LICENSE_IMPORT
        ):
            raise HTTPException(status_code=400, detail="生产环境离线授权必须使用 Challenge-Response")
        return await LicenseService._store_license(
            db,
            license_doc,
            source="offline" if challenge_payload else "import",
            challenge_payload=challenge_payload,
        )

    @staticmethod
    async def activate(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
        activation_code = str(data.get("activation_code") or "").strip()
        customer_id = str(data.get("customer_id") or settings.LICENSE_CUSTOMER_ID or "").strip()
        if not activation_code:
            raise HTTPException(status_code=400, detail="请输入激活码")
        if not customer_id:
            raise HTTPException(status_code=400, detail="请输入客户标识")
        server_data = await LicenseService._call_license_server(
            "/api/v1/licenses/activate",
            {
                "activation_code": activation_code,
                "customer_id": customer_id,
                "deployment_fingerprint": LicenseService.deployment_fingerprint(customer_id),
                **LicenseService._license_server_project_payload(),
            },
        )
        license_doc = server_data.get("license")
        if not license_doc:
            raise HTTPException(status_code=502, detail="授权服务器未返回 License")
        return await LicenseService._store_license(
            db,
            license_doc,
            source="online",
            activation_code=activation_code,
            activation_id=str(server_data.get("activation_id") or ""),
            remote_status=str(server_data.get("status") or "active"),
            server_url=LicenseService._license_server_url(),
        )

    @staticmethod
    async def refresh(db: AsyncSession) -> dict[str, Any]:
        current = await LicenseService._current_record(db)
        if not current or current.source != "online":
            raise HTTPException(status_code=400, detail="当前 License 不是在线激活授权，无法联网续期")
        server_data = await LicenseService._call_license_server(
            "/api/v1/licenses/refresh",
            {
                "activation_id": current.activation_id,
                "license_id": current.license_id,
                "customer_id": current.customer_id,
                "deployment_fingerprint": LicenseService.deployment_fingerprint(current.customer_id),
                **LicenseService._license_server_project_payload(),
            },
        )
        remote_status = str(server_data.get("status") or "active")
        if remote_status in {"revoked", "suspended"}:
            current.status = "invalid"
            current.remote_status = remote_status
            current.last_online_check_at = LicenseService._utcnow()
            current.last_check_status = "invalid"
            current.last_check_reason = "License 已被授权服务器吊销" if remote_status == "revoked" else "License 已被授权服务器冻结"
            await db.commit()
            return await LicenseService.status(db)
        license_doc = server_data.get("license")
        if not license_doc:
            raise HTTPException(status_code=502, detail="授权服务器未返回 License")
        return await LicenseService._store_license(
            db,
            license_doc,
            source="online",
            activation_code=current.activation_code,
            activation_id=str(server_data.get("activation_id") or current.activation_id),
            remote_status=remote_status,
            server_url=LicenseService._license_server_url(),
        )

    @staticmethod
    async def check_access(db: AsyncSession, path: str, method: str) -> LicenseCheck:
        if method.upper() == "OPTIONS" or any(path == p or path.startswith(p + "/") for p in LICENSE_EXEMPT_PREFIXES):
            return LicenseCheck(True, "exempt")
        feature = LicenseService.feature_for_path(path)
        if not feature and not any(path.startswith(prefix) for prefix in LICENSE_PROTECTED_SYSTEM_PREFIXES):
            return LicenseCheck(True, "unprotected")
        state = await LicenseService.status(db)
        status = state["status"]
        if status in {"trial", "licensed"}:
            if status == "licensed" and feature:
                features = set(state.get("features") or [])
                if feature not in features:
                    return LicenseCheck(False, status, f"当前 License 未授权功能：{feature}", feature)
            return LicenseCheck(True, status, feature=feature or "system")
        return LicenseCheck(False, status, state.get("reason") or "License 无效", feature or "system")

    @staticmethod
    def feature_for_path(path: str) -> str:
        for prefix, feature in LICENSE_PROTECTED_FEATURE_BY_PREFIX:
            if path.startswith(prefix):
                return feature
        return ""

    @staticmethod
    async def enforce_limit(db: AsyncSession, limit_name: str, query: Select[Any], label: str) -> None:
        state = await LicenseService.status(db)
        if state["status"] not in {"trial", "licensed"}:
            raise HTTPException(status_code=403, detail=state.get("reason") or "License 无效")
        limits = state.get("limits") or {}
        limit = limits.get(limit_name)
        if limit in (None, "", 0):
            return
        try:
            max_allowed = int(limit)
        except (TypeError, ValueError):
            return
        result = await db.execute(query)
        current = int(result.scalar_one() or 0)
        if current >= max_allowed:
            raise HTTPException(status_code=403, detail=f"{label}数量已达到 License 限额：{max_allowed}")

    @staticmethod
    async def enforce_max_users(db: AsyncSession) -> None:
        await LicenseService.enforce_limit(
            db,
            "max_users",
            select(func.count()).select_from(Users).where(Users.is_active.is_(True)),
            "用户",
        )

    @staticmethod
    async def enforce_max_instances(db: AsyncSession) -> None:
        await LicenseService.enforce_limit(
            db,
            "max_instances",
            select(func.count()).select_from(Instance).where(Instance.is_active.is_(True)),
            "实例",
        )
