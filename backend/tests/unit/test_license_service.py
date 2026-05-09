from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        "project": "sagittadb",
        "product": "sagittadb",
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


def test_verify_license_document_rejects_project_mismatch(keypair, valid_payload):
    valid_payload["project"] = "schemaforge"
    doc = _license_doc(valid_payload, keypair)
    with pytest.raises(HTTPException) as exc:
        LicenseService.verify_license_document(doc)
    assert exc.value.status_code == 400
    assert "授权项目不匹配" in exc.value.detail


def test_verify_license_document_accepts_legacy_payload_without_project(keypair, valid_payload):
    valid_payload.pop("project")
    valid_payload.pop("product")
    doc = _license_doc(valid_payload, keypair)
    payload, _, _ = LicenseService.verify_license_document(doc)
    assert payload["license_id"] == "lic-001"


def test_verify_license_document_rejects_deployment_fingerprint_mismatch(
    monkeypatch, keypair, valid_payload
):
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-a")
    valid_payload["deployment_fingerprint"] = "wrong"
    doc = _license_doc(valid_payload, keypair)
    with pytest.raises(HTTPException) as exc:
        LicenseService.verify_license_document(doc)
    assert exc.value.status_code == 400
    assert "部署指纹不匹配" in exc.value.detail


def test_deployment_fingerprint_uses_customer_and_deployment_id(monkeypatch):
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-a")
    first = LicenseService.deployment_fingerprint("acme")
    second = LicenseService.deployment_fingerprint("other")

    assert len(first) == 64
    assert first != second


def test_offline_challenge_response_success(monkeypatch, keypair, valid_payload):
    monkeypatch.setattr("app.services.license.settings.SECRET_KEY", "secret-for-challenge")
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-a")
    challenge = LicenseService.create_offline_challenge("acme")
    valid_payload["deployment_fingerprint"] = challenge["payload"]["deployment_fingerprint"]
    doc = _license_doc(valid_payload, keypair)

    license_doc, challenge_payload = LicenseService._normalize_import_document(
        {"challenge": challenge, "license": doc}
    )

    assert license_doc == doc
    assert challenge_payload["customer_id"] == "acme"


def test_offline_challenge_response_rejects_unbound_license(monkeypatch, keypair, valid_payload):
    monkeypatch.setattr("app.services.license.settings.SECRET_KEY", "secret-for-challenge")
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-a")
    challenge = LicenseService.create_offline_challenge("acme")
    valid_payload["deployment_fingerprint"] = "wrong"
    doc = _license_doc(valid_payload, keypair)

    with pytest.raises(HTTPException) as exc:
        LicenseService._normalize_import_document({"challenge": challenge, "license": doc})

    assert exc.value.status_code == 400
    assert "部署指纹" in exc.value.detail


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


@pytest.mark.asyncio
async def test_activate_imports_online_license(monkeypatch, keypair, valid_payload):
    doc = _license_doc(valid_payload, keypair)
    call_server = AsyncMock(
        return_value={"status": "active", "activation_id": "act-001", "license": doc}
    )
    store_license = AsyncMock(return_value={"status": "licensed", "license_id": "lic-001"})
    monkeypatch.setattr("app.services.license.settings.LICENSE_SERVER_URL", "http://license.local")
    monkeypatch.setattr(LicenseService, "_call_license_server", call_server)
    monkeypatch.setattr(LicenseService, "_store_license", store_license)

    result = await LicenseService.activate(
        object(),
        {"activation_code": "SGT-001", "customer_id": "acme"},
    )

    assert result["status"] == "licensed"
    call_server.assert_awaited_once()
    request_payload = call_server.await_args.args[1]
    assert request_payload["deployment_fingerprint"]
    assert request_payload["project"] == "sagittadb"
    assert request_payload["product"] == "sagittadb"
    store_license.assert_awaited_once()
    assert store_license.await_args.kwargs["source"] == "online"
    assert store_license.await_args.kwargs["activation_id"] == "act-001"


@pytest.mark.asyncio
async def test_refresh_marks_revoked_license_invalid(monkeypatch):
    record = SimpleNamespace(
        source="online",
        activation_id="act-001",
        license_id="lic-001",
        customer_id="acme",
        status="licensed",
        remote_status="active",
        last_online_check_at=None,
        last_check_status="ok",
        last_check_reason="",
    )
    db = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(LicenseService, "_current_record", AsyncMock(return_value=record))
    monkeypatch.setattr(LicenseService, "_call_license_server", AsyncMock(return_value={"status": "revoked"}))
    monkeypatch.setattr(LicenseService, "status", AsyncMock(return_value={"status": "invalid"}))

    result = await LicenseService.refresh(db)

    assert result["status"] == "invalid"
    request_payload = LicenseService._call_license_server.await_args.args[1]
    assert request_payload["project"] == "sagittadb"
    assert request_payload["product"] == "sagittadb"
    assert record.status == "invalid"
    assert record.remote_status == "revoked"
    assert record.last_check_status == "invalid"
    db.commit.assert_awaited_once()
