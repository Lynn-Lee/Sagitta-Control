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
LICENSE_PROJECT_CODE = "sagitta-control"
LICENSE_PROJECT_NAME = "Sagitta Control"
TRIAL_FEATURES = sorted(LICENSE_FEATURES)
COMMUNITY_STATUS = "community"
# 未登记部署的本地宽限期。刻意不做成配置项：客户可改的 .env 等于没有约束，
# 完整试用期必须由授权中心签发。
# 联网部署：本地只自签一小段宽限，其余试用期必须登记后由授权中心签发。
UNREGISTERED_TRIAL_DAYS = 7
# 内网部署：够不到授权中心，登记与联网签发都走不通，只能靠离线导入。
# 给足搬运 Challenge、走完签发审批的时间，否则客户第一周就被降级。
OFFLINE_TRIAL_DAYS = 30
# 社区版为本地兜底常量，不随 License 下发，保证客户断网到期后仍可降级运行。
COMMUNITY_FEATURES = sorted({"workflow", "query", "instance"})
COMMUNITY_MAX_INSTANCES = 5
COMMUNITY_LIMITS: dict[str, int] = {"max_users": 0, "max_instances": COMMUNITY_MAX_INSTANCES}
# 社区版保留工单提交与查看，仅关闭执行动作。
COMMUNITY_BLOCKED_PATHS: tuple[tuple[str, str], ...] = (
    ("/api/v1/workflow", "/execute"),
)
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
        material = f"sagitta-control:{customer}:{deployment_id}".encode()
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _license_server_project_payload() -> dict[str, str]:
        return {"project": LICENSE_PROJECT_CODE, "product": LICENSE_PROJECT_CODE}

    @staticmethod
    def activation_fingerprint(customer_id: str = "") -> dict[str, str]:
        resolved_customer_id = (customer_id or settings.LICENSE_CUSTOMER_ID).strip()
        if not resolved_customer_id:
            raise HTTPException(status_code=400, detail="请输入客户标识")
        return {
            **LicenseService._license_server_project_payload(),
            "project_code": LICENSE_PROJECT_CODE,
            "project_name": LICENSE_PROJECT_NAME,
            "customer_id": resolved_customer_id,
            "deployment_fingerprint": LicenseService.deployment_fingerprint(resolved_customer_id),
        }

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
        """兼容旧导入格式，并识别用户部署版 challenge-response 响应文件。"""
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
    def local_trial_days() -> int:
        """未配置授权服务器即视为内网部署，放宽本地自签窗口。"""
        return UNREGISTERED_TRIAL_DAYS if settings.LICENSE_SERVER_URL.strip() else OFFLINE_TRIAL_DAYS

    @staticmethod
    async def ensure_trial(db: AsyncSession) -> LicenseRecord:
        current = await LicenseService._current_record(db)
        if current:
            if current.source == "trial" and current.issued_at:
                issued_at = current.issued_at
                expires_at = current.expires_at
                if issued_at.tzinfo is None:
                    issued_at = issued_at.replace(tzinfo=UTC)
                if expires_at and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                configured_expires_at = issued_at + timedelta(days=LicenseService.local_trial_days())
                if not expires_at or expires_at < configured_expires_at:
                    current.expires_at = configured_expires_at
                    current.last_check_status = "ok"
                    current.last_check_reason = "试用期内"
                    await db.commit()
                    await db.refresh(current)
            return current
        now = LicenseService._utcnow()
        trial = LicenseRecord(
            source="trial",
            status="trial",
            is_current=True,
            license_id="trial",
            customer_id=settings.LICENSE_CUSTOMER_ID or "trial",
            company_name="未登记试用",
            edition="trial",
            features=TRIAL_FEATURES,
            limits={},
            issued_at=now,
            not_before=now,
            expires_at=now + timedelta(days=LicenseService.local_trial_days()),
            last_check_status="ok",
            last_check_reason="未登记试用期内",
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
        last_online_check_at = record.last_online_check_at
        if not_before and not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=UTC)
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if last_online_check_at and last_online_check_at.tzinfo is None:
            last_online_check_at = last_online_check_at.replace(tzinfo=UTC)
        if not_before and now < not_before:
            return "invalid", "License 尚未生效"
        if expires_at and now > expires_at:
            return COMMUNITY_STATUS, "试用/授权已到期，已降级为社区版"
        if record.status == "invalid":
            return "invalid", record.last_check_reason or "License 无效"
        if record.source == "online" and settings.LICENSE_ONLINE_GRACE_DAYS > 0:
            grace_anchor = last_online_check_at or record.issued_at
            if grace_anchor and grace_anchor.tzinfo is None:
                grace_anchor = grace_anchor.replace(tzinfo=UTC)
            if not grace_anchor:
                return "invalid", "在线 License 尚未完成联网校验"
            if now - grace_anchor > timedelta(days=settings.LICENSE_ONLINE_GRACE_DAYS):
                return COMMUNITY_STATUS, "超过联网校验宽限期，已降级为社区版，请恢复联网或刷新授权"
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
        if status == COMMUNITY_STATUS:
            warning_level = "critical"
        elif status in {"trial", "licensed"} and days_remaining is not None:
            if days_remaining <= 7:
                warning_level = "critical"
            elif days_remaining <= 30:
                warning_level = "warning"
        if status == COMMUNITY_STATUS:
            features: list[str] = list(COMMUNITY_FEATURES)
            limits: dict[str, Any] = dict(COMMUNITY_LIMITS)
        else:
            features = list(record.features or [])
            limits = dict(record.limits or {})
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
            "edition": COMMUNITY_STATUS if status == COMMUNITY_STATUS else record.edition,
            "features": features,
            "limits": limits,
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
        await LicenseService.sync_instance_suspension(db)
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
    def trial_customer_id() -> str:
        """未登记部署的稳定客户标识，保证登记前后指纹一致。"""
        configured = settings.LICENSE_CUSTOMER_ID.strip()
        if configured:
            return configured
        seed = settings.LICENSE_DEPLOYMENT_ID.strip() or settings.SECRET_KEY.strip()
        digest = hashlib.sha256(f"sagitta-control-trial:{seed}".encode()).hexdigest()
        return f"TRIAL-{digest[:16].upper()}"

    @staticmethod
    async def send_trial_code(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
        """自助试用第一步：让授权中心向登记邮箱发送验证码。"""
        contact_email = str(data.get("contact_email") or "").strip()
        if not contact_email:
            raise HTTPException(status_code=400, detail="请填写联系邮箱")
        customer_id = LicenseService.trial_customer_id()
        return await LicenseService._call_license_server(
            "/api/v1/licenses/trial/send-code",
            {
                "customer_id": customer_id,
                "contact_email": contact_email,
                "contact_phone": str(data.get("contact_phone") or "").strip(),
                **LicenseService._license_server_project_payload(),
            },
        )

    @staticmethod
    async def request_trial(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
        """登记企业与联系人信息，向授权中心换取完整试用 License。"""
        from app.services.commercial_ops import CommercialOpsService

        company_name = str(data.get("company_name") or "").strip()
        contact_name = str(data.get("contact_name") or "").strip()
        contact_email = str(data.get("contact_email") or "").strip()
        contact_phone = str(data.get("contact_phone") or "").strip()
        if not company_name or not contact_name or not contact_email:
            raise HTTPException(status_code=400, detail="请填写企业名称、联系人与联系邮箱")
        customer_id = LicenseService.trial_customer_id()
        server_data = await LicenseService._call_license_server(
            "/api/v1/licenses/trial",
            {
                "customer_id": customer_id,
                "company_name": company_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "verification_code": str(data.get("verification_code") or "").strip(),
                "deployment_fingerprint": LicenseService.deployment_fingerprint(customer_id),
                "usage": await CommercialOpsService.usage_payload(db),
                "runtime": await CommercialOpsService.runtime_payload(db, "trial"),
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
            activation_id=str(server_data.get("activation_id") or ""),
            remote_status=str(server_data.get("status") or "active"),
            server_url=LicenseService._license_server_url(),
        )

    @staticmethod
    async def activate(db: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
        from app.services.commercial_ops import CommercialOpsService

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
                "usage": await CommercialOpsService.usage_payload(db),
                "runtime": await CommercialOpsService.runtime_payload(db, "activation"),
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
        from app.services.commercial_ops import CommercialOpsService

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
                "usage": await CommercialOpsService.usage_payload(db),
                "runtime": await CommercialOpsService.runtime_payload(db, current.source),
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
        if status == COMMUNITY_STATUS:
            blocked = LicenseService.community_block_reason(path)
            if blocked:
                return LicenseCheck(False, status, blocked, feature or "system")
            if feature and feature not in COMMUNITY_FEATURES:
                return LicenseCheck(False, status, f"社区版未包含该功能：{feature}，升级正式授权后可用", feature)
            return LicenseCheck(True, status, feature=feature or "system")
        if status in {"trial", "licensed"}:
            if status == "licensed" and feature:
                features = set(state.get("features") or [])
                if feature not in features:
                    return LicenseCheck(False, status, f"当前 License 未授权功能：{feature}", feature)
            return LicenseCheck(True, status, feature=feature or "system")
        return LicenseCheck(False, status, state.get("reason") or "License 无效", feature or "system")

    @staticmethod
    def community_block_reason(path: str) -> str:
        """社区版下被关闭的动作，返回空串表示放行。"""
        for prefix, marker in COMMUNITY_BLOCKED_PATHS:
            if path.startswith(prefix) and marker in path:
                return "社区版不支持工单执行，升级正式授权后可用"
        return ""

    @staticmethod
    def feature_for_path(path: str) -> str:
        for prefix, feature in LICENSE_PROTECTED_FEATURE_BY_PREFIX:
            if path.startswith(prefix):
                return feature
        return ""

    @staticmethod
    async def enforce_limit(db: AsyncSession, limit_name: str, query: Select[Any], label: str) -> None:
        state = await LicenseService.status(db)
        if state["status"] not in {"trial", "licensed", COMMUNITY_STATUS}:
            raise HTTPException(status_code=403, detail=state.get("reason") or "License 无效")
        limits = state.get("limits") or {}
        limit = limits.get(limit_name)
        if limit in (None, "", 0):
            return
        try:
            max_allowed = int(limit)  # type: ignore[arg-type]
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
    def _max_instances(state: dict[str, Any]) -> int:
        limits = state.get("limits") or {}
        try:
            return int(limits.get("max_instances") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    async def sync_instance_suspension(db: AsyncSession) -> dict[str, int]:
        """按当前额度同步实例挂起状态：超额实例挂起，额度恢复后自动解挂。

        只标记不删除，升级正式授权后原样恢复，客户无需重新配置。
        """
        state = await LicenseService.status(db)
        if state["status"] not in {"trial", "licensed", COMMUNITY_STATUS}:
            return {"suspended": 0, "restored": 0}
        max_instances = LicenseService._max_instances(state)
        result = await db.execute(
            select(Instance.id, Instance.license_suspended)
            .where(Instance.is_active.is_(True))
            .order_by(Instance.created_at.asc(), Instance.id.asc())
        )
        rows = [(int(row[0]), bool(row[1])) for row in result.all()]
        instance_ids = [item for item, _ in rows]
        kept = [item for item, suspended in rows if not suspended]
        if max_instances <= 0 or len(instance_ids) <= max_instances:
            keep_ids = instance_ids
        elif len(kept) > max_instances:
            # 首次降级或额度收紧：按创建时间保留最早的若干个。
            keep_ids = kept[:max_instances]
        else:
            # 已在额度内，尊重现有选择，不把用户手动挂起的实例重新拉回来。
            keep_ids = kept
        suspend_ids = [item for item in instance_ids if item not in set(keep_ids)]
        restored = 0
        suspended = 0
        if keep_ids:
            outcome = await db.execute(
                update(Instance)
                .where(Instance.id.in_(keep_ids), Instance.license_suspended.is_(True))
                .values(license_suspended=False)
            )
            restored = int(getattr(outcome, "rowcount", 0) or 0)
        if suspend_ids:
            outcome = await db.execute(
                update(Instance)
                .where(Instance.id.in_(suspend_ids), Instance.license_suspended.is_(False))
                .values(license_suspended=True)
            )
            suspended = int(getattr(outcome, "rowcount", 0) or 0)
        if restored or suspended:
            await db.commit()
        return {"suspended": suspended, "restored": restored}

    @staticmethod
    async def instance_allocation(db: AsyncSession) -> dict[str, Any]:
        """额度分配视图：当前额度、已启用与被挂起的实例。"""
        state = await LicenseService.status(db)
        max_instances = LicenseService._max_instances(state)
        result = await db.execute(
            select(Instance.id, Instance.instance_name, Instance.db_type, Instance.license_suspended)
            .where(Instance.is_active.is_(True))
            .order_by(Instance.created_at.asc(), Instance.id.asc())
        )
        items = [
            {
                "id": int(row[0]),
                "instance_name": row[1],
                "db_type": row[2],
                "license_suspended": bool(row[3]),
            }
            for row in result.all()
        ]
        return {
            "status": state["status"],
            "max_instances": max_instances,
            "active_total": len(items),
            "enabled_total": sum(1 for item in items if not item["license_suspended"]),
            "selectable": max_instances > 0 and len(items) > max_instances,
            "instances": items,
        }

    @staticmethod
    async def select_active_instances(db: AsyncSession, instance_ids: list[int]) -> dict[str, Any]:
        """手动指定额度内启用哪些实例，未选中的挂起但保留配置。"""
        state = await LicenseService.status(db)
        max_instances = LicenseService._max_instances(state)
        if max_instances <= 0:
            raise HTTPException(status_code=400, detail="当前授权不限实例数，无需手动选择")
        selected = list(dict.fromkeys(int(item) for item in instance_ids))
        if not selected:
            raise HTTPException(status_code=400, detail="请至少选择一个实例")
        if len(selected) > max_instances:
            raise HTTPException(status_code=400, detail=f"当前授权最多启用 {max_instances} 个实例")
        result = await db.execute(select(Instance.id).where(Instance.is_active.is_(True)))
        active_ids = {int(row[0]) for row in result.all()}
        if not set(selected).issubset(active_ids):
            raise HTTPException(status_code=400, detail="选择中包含不存在或已停用的实例")
        await db.execute(
            update(Instance)
            .where(Instance.id.in_(selected), Instance.license_suspended.is_(True))
            .values(license_suspended=False)
        )
        rest = [item for item in active_ids if item not in set(selected)]
        if rest:
            await db.execute(
                update(Instance)
                .where(Instance.id.in_(rest), Instance.license_suspended.is_(False))
                .values(license_suspended=True)
            )
        await db.commit()
        return await LicenseService.instance_allocation(db)

    @staticmethod
    async def enforce_max_instances(db: AsyncSession) -> None:
        await LicenseService.enforce_limit(
            db,
            "max_instances",
            select(func.count()).select_from(Instance).where(Instance.is_active.is_(True)),
            "实例",
        )
