from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.core.exceptions import AppException
from app.services import sms_auth
from app.services.system_config import SystemConfigService


class FakePipeline:
    def __init__(self) -> None:
        self.ops: list[tuple[str, str, int | None]] = []
        self.executed = False

    def incr(self, key: str) -> None:
        self.ops.append(("incr", key, None))

    def expire(self, key: str, seconds: int) -> None:
        self.ops.append(("expire", key, seconds))

    async def execute(self) -> None:
        self.executed = True


class FakeRedis:
    def __init__(
        self,
        *,
        existing_keys: set[str] | None = None,
        values: dict[str, str | None] | None = None,
        ttls: dict[str, int] | None = None,
    ) -> None:
        self.existing_keys = existing_keys or set()
        self.values = values or {}
        self.ttls = ttls or {}
        self.setex_calls: list[tuple[str, int, str]] = []
        self.deleted: list[str] = []
        self.closed = False
        self.pipe = FakePipeline()

    async def exists(self, key: str) -> bool:
        return key in self.existing_keys

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self.setex_calls.append((key, seconds, value))
        self.values[key] = value

    def pipeline(self) -> FakePipeline:
        return self.pipe

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)

    async def aclose(self) -> None:
        self.closed = True


def patch_config(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str]
) -> Callable[[Any, str], Any]:
    async def get_value(db: Any, key: str) -> str:
        return values.get(key, "")

    monkeypatch.setattr(SystemConfigService, "get_value", get_value)
    return get_value


def patch_redis(monkeypatch: pytest.MonkeyPatch, redis: FakeRedis) -> FakeRedis:
    async def get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(sms_auth, "_get_redis", get_redis)
    return redis


@pytest.mark.asyncio
async def test_send_sms_code_requires_enabled_config(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_config(monkeypatch, {"sms_enabled": "false"})

    with pytest.raises(AppException) as exc:
        await sms_auth.send_sms_code(object(), "13800000000")  # type: ignore[arg-type]

    assert exc.value.code == 400
    assert exc.value.message == "短信验证码登录未启用"


@pytest.mark.asyncio
async def test_send_sms_code_rejects_cooldown_and_closes_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13800000000"
    redis = patch_redis(
        monkeypatch,
        FakeRedis(existing_keys={f"sms:cooldown:{phone}"}, ttls={f"sms:cooldown:{phone}": 42}),
    )
    patch_config(monkeypatch, {"sms_enabled": "true"})

    with pytest.raises(AppException) as exc:
        await sms_auth.send_sms_code(object(), phone)  # type: ignore[arg-type]

    assert exc.value.code == 429
    assert "42 秒后再试" in exc.value.message
    assert redis.closed is True


@pytest.mark.asyncio
async def test_send_sms_code_rejects_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    phone = "13800000000"
    redis = patch_redis(
        monkeypatch,
        FakeRedis(values={f"sms:daily:{phone}": str(sms_auth.DAILY_LIMIT)}),
    )
    patch_config(monkeypatch, {"sms_enabled": "true"})

    with pytest.raises(AppException) as exc:
        await sms_auth.send_sms_code(object(), phone)  # type: ignore[arg-type]

    assert exc.value.code == 429
    assert exc.value.message == "今日验证码发送次数已达上限"
    assert redis.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "sender_name"),
    [
        ("aliyun", "_send_aliyun"),
        ("tencent", "_send_tencent"),
        ("custom", "_send_custom"),
        ("unknown", "_send_aliyun"),
    ],
)
async def test_send_sms_code_stores_limits_and_dispatches_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str, sender_name: str
) -> None:
    phone = "13800000000"
    redis = patch_redis(monkeypatch, FakeRedis())
    patch_config(monkeypatch, {"sms_enabled": "true", "sms_provider": provider})
    monkeypatch.setattr(sms_auth.random, "choices", lambda *args, **kwargs: list("123456"))
    sent: list[tuple[str, str, str]] = []

    async def fake_sender(db: Any, target_phone: str, code: str) -> dict[str, Any]:
        sent.append((sender_name, target_phone, code))
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(sms_auth, sender_name, fake_sender)

    result = await sms_auth.send_sms_code(object(), phone)  # type: ignore[arg-type]

    assert result == {"success": True, "message": "ok"}
    assert (f"sms:code:{phone}", sms_auth.CODE_TTL_SECONDS, "123456") in redis.setex_calls
    assert (f"sms:cooldown:{phone}", sms_auth.CODE_COOLDOWN_SECONDS, "1") in redis.setex_calls
    assert redis.pipe.ops == [
        ("incr", f"sms:daily:{phone}", None),
        ("expire", f"sms:daily:{phone}", 86400),
    ]
    assert redis.pipe.executed is True
    assert sent == [(sender_name, phone, "123456")]
    assert redis.closed is True


@pytest.mark.asyncio
async def test_verify_sms_code_returns_false_when_code_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = patch_redis(monkeypatch, FakeRedis())

    assert await sms_auth.verify_sms_code("13800000000", "123456") is False
    assert redis.deleted == []
    assert redis.closed is True


@pytest.mark.asyncio
async def test_verify_sms_code_returns_false_for_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13800000000"
    redis = patch_redis(monkeypatch, FakeRedis(values={f"sms:code:{phone}": "654321"}))

    assert await sms_auth.verify_sms_code(phone, "123456") is False
    assert redis.deleted == []
    assert redis.closed is True


@pytest.mark.asyncio
async def test_verify_sms_code_deletes_code_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "13800000000"
    redis = patch_redis(monkeypatch, FakeRedis(values={f"sms:code:{phone}": "123456"}))

    assert await sms_auth.verify_sms_code(phone, "123456") is True
    assert redis.deleted == [f"sms:code:{phone}"]
    assert redis.closed is True


@pytest.mark.asyncio
async def test_send_aliyun_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_config(monkeypatch, {"sms_access_key_id": "", "sms_access_key_secret": ""})

    result = await sms_auth._send_aliyun(object(), "13800000000", "123456")  # type: ignore[arg-type]

    assert result == {"success": False, "message": "阿里云短信配置不完整"}


@pytest.mark.asyncio
async def test_send_tencent_returns_placeholder_success() -> None:
    result = await sms_auth._send_tencent(object(), "13800000000", "123456")  # type: ignore[arg-type]

    assert result["success"] is True
    assert "腾讯云短信 SDK" in result["message"]


@pytest.mark.asyncio
async def test_send_custom_requires_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_config(monkeypatch, {"sms_endpoint": ""})

    result = await sms_auth._send_custom(object(), "13800000000", "123456")  # type: ignore[arg-type]

    assert result == {"success": False, "message": "自定义短信 API 端点未配置"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_data", "expected"),
    [
        ({"Code": "OK"}, {"success": True, "message": "验证码已发送"}),
        (
            {"Code": "Invalid", "Message": "签名错误"},
            {"success": False, "message": "发送失败：签名错误"},
        ),
    ],
)
async def test_send_aliyun_maps_provider_response(
    monkeypatch: pytest.MonkeyPatch,
    response_data: dict[str, str],
    expected: dict[str, Any],
) -> None:
    patch_config(
        monkeypatch,
        {
            "sms_access_key_id": "ak",
            "sms_access_key_secret": "secret",
            "sms_sign_name": "Sagitta",
            "sms_template_code": "SMS_001",
        },
    )
    requested_urls: list[str] = []

    class FakeResponse:
        def json(self) -> dict[str, str]:
            return response_data

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, url: str) -> FakeResponse:
            requested_urls.append(url)
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    result = await sms_auth._send_aliyun(object(), "13800000000", "123456")  # type: ignore[arg-type]

    assert result == expected
    assert requested_urls
    assert "PhoneNumbers=13800000000" in requested_urls[0]
    assert "TemplateCode=SMS_001" in requested_urls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (200, {"success": True, "message": "验证码已发送"}),
        (500, {"success": False, "message": "自定义短信服务返回 500"}),
    ],
)
async def test_send_custom_maps_http_status(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: dict[str, Any],
) -> None:
    patch_config(monkeypatch, {"sms_endpoint": "https://sms.example.test/send"})
    requests: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, status: int) -> None:
            self.status_code = status

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(self, endpoint: str, json: dict[str, str]) -> FakeResponse:
            requests.append((endpoint, json))
            return FakeResponse(status_code)

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    result = await sms_auth._send_custom(object(), "13800000000", "123456")  # type: ignore[arg-type]

    assert result == expected
    assert requests == [
        ("https://sms.example.test/send", {"phone": "13800000000", "code": "123456"})
    ]
