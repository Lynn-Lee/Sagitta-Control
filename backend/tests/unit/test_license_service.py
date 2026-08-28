from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app.models.system import LicenseRecord
from app.services.license import (
    COMMUNITY_FEATURES,
    COMMUNITY_LIMITS,
    COMMUNITY_STATUS,
    OFFLINE_TRIAL_DAYS,
    UNREGISTERED_TRIAL_DAYS,
    LicenseService,
)


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
        "project": "sagitta-control",
        "product": "sagitta-control",
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


@pytest.mark.asyncio
async def test_status_uses_sagitta_control_display_name(monkeypatch):
    record = LicenseRecord(
        source="trial",
        status="trial",
        is_current=True,
        license_id="trial",
        customer_id="trial",
        company_name="试用版",
        edition="trial",
        features=[],
        limits={},
        issued_at=datetime.now(UTC),
        not_before=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=60),
        last_check_status="trial",
        last_check_reason="试用期内",
    )
    monkeypatch.setattr(LicenseService, "ensure_trial", AsyncMock(return_value=record))

    result = await LicenseService.status(SimpleNamespace(commit=AsyncMock()))

    assert result["project_code"] == "sagitta-control"
    assert result["project_name"] == "Sagitta Control"


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
    # 到期不再锁死，降级为社区版。
    assert LicenseService.evaluate_record(expired)[0] == "community"

    future = LicenseRecord(
        source="import",
        status="licensed",
        not_before=now + timedelta(days=1),
        expires_at=now + timedelta(days=10),
    )
    assert LicenseService.evaluate_record(future)[0] == "invalid"


def test_evaluate_online_record_requires_recent_server_check(monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr("app.services.license.settings.LICENSE_ONLINE_GRACE_DAYS", 7)
    stale = LicenseRecord(
        source="online",
        status="licensed",
        issued_at=now - timedelta(days=30),
        not_before=now - timedelta(days=30),
        expires_at=now + timedelta(days=30),
        last_online_check_at=now - timedelta(days=8),
    )
    assert LicenseService.evaluate_record(stale)[0] == COMMUNITY_STATUS

    fresh = LicenseRecord(
        source="online",
        status="licensed",
        issued_at=now - timedelta(days=30),
        not_before=now - timedelta(days=30),
        expires_at=now + timedelta(days=30),
        last_online_check_at=now - timedelta(days=1),
    )
    assert LicenseService.evaluate_record(fresh)[0] == "licensed"


@pytest.mark.asyncio
async def test_ensure_trial_extends_existing_trial_to_configured_days(monkeypatch):
    issued_at = datetime.now(UTC) - timedelta(days=1)
    record = LicenseRecord(
        source="trial",
        status="trial",
        is_current=True,
        license_id="trial",
        customer_id="trial",
        company_name="试用版",
        edition="trial",
        features=[],
        limits={},
        issued_at=issued_at,
        not_before=issued_at,
        expires_at=issued_at + timedelta(days=1),
        last_check_status="expired",
        last_check_reason="License 已过期",
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(LicenseService, "_current_record", AsyncMock(return_value=record))

    result = await LicenseService.ensure_trial(db)

    assert result is record
    assert record.expires_at == issued_at + timedelta(days=UNREGISTERED_TRIAL_DAYS)
    assert record.last_check_status == "ok"
    assert record.last_check_reason == "试用期内"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(record)


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
    assert request_payload["project"] == "sagitta-control"
    assert request_payload["product"] == "sagitta-control"
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
    assert request_payload["project"] == "sagitta-control"
    assert request_payload["product"] == "sagitta-control"
    assert record.status == "invalid"
    assert record.remote_status == "revoked"
    assert record.last_check_status == "invalid"
    db.commit.assert_awaited_once()


def _community_status() -> dict:
    return {
        "status": COMMUNITY_STATUS,
        "reason": "试用/授权已到期，已降级为社区版",
        "features": list(COMMUNITY_FEATURES),
        "limits": dict(COMMUNITY_LIMITS),
    }


@pytest.mark.asyncio
async def test_community_allows_query_and_workflow_submit(monkeypatch):
    async def fake_status(_db):
        return _community_status()

    monkeypatch.setattr(LicenseService, "status", fake_status)
    for path in ("/api/v1/query/execute", "/api/v1/workflow/", "/api/v1/instances/"):
        check = await LicenseService.check_access(object(), path, "POST")
        assert check.allowed, path
        assert check.status == COMMUNITY_STATUS


@pytest.mark.asyncio
async def test_community_blocks_workflow_execute(monkeypatch):
    async def fake_status(_db):
        return _community_status()

    monkeypatch.setattr(LicenseService, "status", fake_status)
    check = await LicenseService.check_access(object(), "/api/v1/workflow/12/execute/", "POST")
    assert not check.allowed
    assert "工单执行" in check.reason


@pytest.mark.asyncio
async def test_community_blocks_uncovered_features(monkeypatch):
    async def fake_status(_db):
        return _community_status()

    monkeypatch.setattr(LicenseService, "status", fake_status)
    for path, feature in (
        ("/api/v1/archive/tasks", "archive"),
        ("/api/v1/monitor/sessions", "monitor"),
        ("/api/v1/masking/rules", "masking"),
        ("/api/v1/ai/explain", "ai"),
    ):
        check = await LicenseService.check_access(object(), path, "POST")
        assert not check.allowed, path
        assert check.feature == feature


@pytest.mark.asyncio
async def test_community_keeps_system_management_available(monkeypatch):
    async def fake_status(_db):
        return _community_status()

    monkeypatch.setattr(LicenseService, "status", fake_status)
    check = await LicenseService.check_access(object(), "/api/v1/system/users", "POST")
    assert check.allowed


@pytest.mark.asyncio
async def test_community_limits_instances_but_not_users():
    assert COMMUNITY_LIMITS["max_instances"] == 5
    # 0 表示不限：共用账号会摧毁审计追溯，社区版同样不限用户数。
    assert COMMUNITY_LIMITS["max_users"] == 0


def test_trial_customer_id_is_stable_and_matches_fingerprint(monkeypatch):
    monkeypatch.setattr("app.services.license.settings.LICENSE_CUSTOMER_ID", "")
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-001")

    customer_id = LicenseService.trial_customer_id()
    assert customer_id.startswith("TRIAL-")
    # 同一部署必须稳定，否则登记前后指纹不一致，License 会校验失败。
    assert LicenseService.trial_customer_id() == customer_id

    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-002")
    assert LicenseService.trial_customer_id() != customer_id


def test_trial_customer_id_prefers_configured_customer(monkeypatch):
    monkeypatch.setattr("app.services.license.settings.LICENSE_CUSTOMER_ID", "CUST-9527")
    assert LicenseService.trial_customer_id() == "CUST-9527"


@pytest.mark.asyncio
async def test_request_trial_requires_contact_fields():
    with pytest.raises(HTTPException) as exc:
        await LicenseService.request_trial(object(), {"company_name": "只填了企业"})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_request_trial_posts_registration_and_stores_license(monkeypatch):
    monkeypatch.setattr("app.services.license.settings.LICENSE_CUSTOMER_ID", "")
    monkeypatch.setattr("app.services.license.settings.LICENSE_DEPLOYMENT_ID", "deploy-001")
    monkeypatch.setattr("app.services.license.settings.LICENSE_SERVER_URL", "https://license.example.com")

    from app.services import commercial_ops

    monkeypatch.setattr(
        commercial_ops.CommercialOpsService, "usage_payload", AsyncMock(return_value={"instances": 3})
    )
    monkeypatch.setattr(
        commercial_ops.CommercialOpsService, "runtime_payload", AsyncMock(return_value={"version": "3.0"})
    )
    call_server = AsyncMock(return_value={"status": "active", "activation_id": "act-t1", "license": {"payload": {}}})
    monkeypatch.setattr(LicenseService, "_call_license_server", call_server)
    store = AsyncMock(return_value={"status": "trial"})
    monkeypatch.setattr(LicenseService, "_store_license", store)

    await LicenseService.request_trial(
        object(),
        {
            "company_name": " 示例物流 ",
            "contact_name": " 张三 ",
            "contact_email": " zhangsan@example.com ",
            "contact_phone": " 13800000000 ",
        },
    )

    endpoint, body = call_server.await_args.args
    assert endpoint == "/api/v1/licenses/trial"
    assert body["company_name"] == "示例物流"
    assert body["contact_email"] == "zhangsan@example.com"
    expected_customer = LicenseService.trial_customer_id()
    assert body["customer_id"] == expected_customer
    # 指纹必须由同一个 customer_id 推导，否则服务端签发的 License 本地校验不过。
    assert body["deployment_fingerprint"] == LicenseService.deployment_fingerprint(expected_customer)
    assert store.await_args.kwargs["source"] == "online"
    assert store.await_args.kwargs["activation_id"] == "act-t1"


def _allocation_rows(count: int, suspended_ids: set[int] | None = None):
    suspended = suspended_ids or set()
    return [(i, i in suspended) for i in range(1, count + 1)]


@pytest.mark.asyncio
async def test_sync_suspension_keeps_oldest_on_first_downgrade(monkeypatch):
    monkeypatch.setattr(
        LicenseService, "status", AsyncMock(return_value={"status": COMMUNITY_STATUS, "limits": {"max_instances": 5}})
    )
    captured = {}

    async def fake_execute(statement):
        if "SELECT" in str(statement).upper() and "license_suspended" in str(statement):
            return SimpleNamespace(all=lambda: _allocation_rows(8))
        captured.setdefault("updates", []).append(str(statement))
        return SimpleNamespace(rowcount=3)

    db = SimpleNamespace(execute=fake_execute, commit=AsyncMock())
    result = await LicenseService.sync_instance_suspension(db)
    assert result["suspended"] == 3


@pytest.mark.asyncio
async def test_sync_suspension_respects_manual_selection(monkeypatch):
    """已在额度内时不得把用户手动挂起的实例重新拉回来。"""
    monkeypatch.setattr(
        LicenseService, "status", AsyncMock(return_value={"status": COMMUNITY_STATUS, "limits": {"max_instances": 5}})
    )
    # 8 个实例，用户手动只留了 3 个（挂起 4-8），已在额度内。
    rows = _allocation_rows(8, suspended_ids={4, 5, 6, 7, 8})
    updates: list[str] = []

    async def fake_execute(statement):
        text = str(statement)
        if text.upper().startswith("SELECT") and "license_suspended" in text:
            return SimpleNamespace(all=lambda: rows)
        updates.append(text)
        return SimpleNamespace(rowcount=0)

    db = SimpleNamespace(execute=fake_execute, commit=AsyncMock())
    result = await LicenseService.sync_instance_suspension(db)
    assert result == {"suspended": 0, "restored": 0}
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_select_active_instances_rejects_over_quota(monkeypatch):
    monkeypatch.setattr(
        LicenseService, "status", AsyncMock(return_value={"status": COMMUNITY_STATUS, "limits": {"max_instances": 5}})
    )
    with pytest.raises(HTTPException) as exc:
        await LicenseService.select_active_instances(object(), [1, 2, 3, 4, 5, 6])
    assert exc.value.status_code == 400
    assert "最多启用 5" in exc.value.detail


@pytest.mark.asyncio
async def test_select_active_instances_rejects_empty(monkeypatch):
    monkeypatch.setattr(
        LicenseService, "status", AsyncMock(return_value={"status": COMMUNITY_STATUS, "limits": {"max_instances": 5}})
    )
    with pytest.raises(HTTPException) as exc:
        await LicenseService.select_active_instances(object(), [])
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_select_active_instances_noop_when_unlimited(monkeypatch):
    monkeypatch.setattr(
        LicenseService, "status", AsyncMock(return_value={"status": "licensed", "limits": {"max_instances": 0}})
    )
    with pytest.raises(HTTPException) as exc:
        await LicenseService.select_active_instances(object(), [1])
    assert "不限实例数" in exc.value.detail


def test_local_trial_days_follows_deployment_mode(monkeypatch):
    """联网部署给 7 天宽限；内网够不到授权中心，必须放宽到 30 天。"""
    monkeypatch.setattr("app.services.license.settings.LICENSE_SERVER_URL", "https://license.loveai.asia")
    assert LicenseService.local_trial_days() == UNREGISTERED_TRIAL_DAYS == 7

    monkeypatch.setattr("app.services.license.settings.LICENSE_SERVER_URL", "   ")
    assert LicenseService.local_trial_days() == OFFLINE_TRIAL_DAYS == 30


@pytest.mark.asyncio
async def test_ensure_trial_uses_offline_window_when_no_server(monkeypatch):
    monkeypatch.setattr("app.services.license.settings.LICENSE_SERVER_URL", "")
    monkeypatch.setattr(LicenseService, "_current_record", AsyncMock(return_value=None))
    added: list[LicenseRecord] = []
    db = SimpleNamespace(add=added.append, commit=AsyncMock(), refresh=AsyncMock())

    record = await LicenseService.ensure_trial(db)

    assert record.source == "trial"
    span = record.expires_at - record.issued_at
    assert span == timedelta(days=OFFLINE_TRIAL_DAYS)
