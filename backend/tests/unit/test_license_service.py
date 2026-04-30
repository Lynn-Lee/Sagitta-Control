from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app.models.system import LicenseRecord
from app.services.license import LicenseService


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _license_doc(payload: dict, private_key: Ed25519PrivateKey) -> dict:
    return {
        "payload": payload,
        "signature": _b64url(private_key.sign(LicenseService._canonical_payload(payload))),
    }


@pytest.fixture()
def keypair(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setattr("app.services.license.settings.LICENSE_PUBLIC_KEY", _b64url(public_key))
    monkeypatch.setattr("app.services.license.settings.LICENSE_CUSTOMER_ID", "acme")
    return private_key


@pytest.fixture()
def valid_payload():
    now = datetime.now(UTC)
    return {
        "license_id": "lic-001",
        "customer_id": "acme",
        "company_name": "Acme Corp",
        "edition": "enterprise",
        "issued_at": now.isoformat(),
        "not_before": now.isoformat(),
        "expires_at": (now + timedelta(days=365)).isoformat(),
        "features": ["workflow", "query", "instance"],
        "limits": {"max_instances": 3, "max_users": 10},
    }


def test_verify_license_document_success(keypair, valid_payload):
    doc = _license_doc(valid_payload, keypair)
    payload, signature, raw = LicenseService.verify_license_document(doc)
    assert payload["license_id"] == "lic-001"
    assert signature == doc["signature"]
    assert "Acme Corp" in raw


def test_verify_license_document_rejects_tampered_payload(keypair, valid_payload):
    doc = _license_doc(valid_payload, keypair)
    doc["payload"]["edition"] = "enterprise-plus"
    with pytest.raises(HTTPException) as exc:
        LicenseService.verify_license_document(doc)
    assert exc.value.status_code == 400
    assert "签名无效" in exc.value.detail


def test_verify_license_document_rejects_customer_mismatch(keypair, valid_payload):
    valid_payload["customer_id"] = "other"
    doc = _license_doc(valid_payload, keypair)
    with pytest.raises(HTTPException) as exc:
        LicenseService.verify_license_document(doc)
    assert exc.value.status_code == 400
    assert "客户标识不匹配" in exc.value.detail


def test_evaluate_record_expired_and_not_before():
    now = datetime.now(UTC)
    expired = LicenseRecord(
        source="import",
        status="licensed",
        not_before=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
    )
    assert LicenseService.evaluate_record(expired)[0] == "expired"

    future = LicenseRecord(
        source="import",
        status="licensed",
        not_before=now + timedelta(days=1),
        expires_at=now + timedelta(days=10),
    )
    assert LicenseService.evaluate_record(future)[0] == "invalid"


@pytest.mark.asyncio
async def test_check_access_rejects_expired_license(monkeypatch):
    async def fake_status(_db):
        return {"status": "expired", "reason": "License 已过期", "features": []}

    monkeypatch.setattr(LicenseService, "status", fake_status)
    check = await LicenseService.check_access(object(), "/api/v1/query/execute", "POST")
    assert not check.allowed
    assert check.status == "expired"


@pytest.mark.asyncio
async def test_check_access_rejects_missing_feature(monkeypatch):
    async def fake_status(_db):
        return {"status": "licensed", "reason": "ok", "features": ["workflow"]}

    monkeypatch.setattr(LicenseService, "status", fake_status)
    check = await LicenseService.check_access(object(), "/api/v1/query/execute", "POST")
    assert not check.allowed
    assert check.feature == "query"
