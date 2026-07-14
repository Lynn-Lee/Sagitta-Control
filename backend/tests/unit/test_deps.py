from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import HTTPException
from jwt import PyJWTError

from app.core import deps


@dataclass
class FakePermission:
    codename: str


@dataclass
class FakeRole:
    name: str
    permissions: list[FakePermission]


@dataclass
class FakeResourceGroup:
    id: int


@dataclass
class FakeUserGroup:
    id: int
    resource_groups: list[FakeResourceGroup]


class FakeDbUser:
    id = 7
    username = "alice"
    display_name = "Alice"
    is_superuser = False
    is_active = True
    role_id = 3
    manager_id = 2
    tenant_id = 1
    password_changed_at = None
    role = FakeRole("engineer", [FakePermission("query:read"), FakePermission("audit:view")])
    user_groups = [FakeUserGroup(5, [FakeResourceGroup(10), FakeResourceGroup(20)])]


class FakeResult:
    def __init__(self, user: FakeDbUser | None) -> None:
        self.user = user

    def scalar_one_or_none(self) -> FakeDbUser | None:
        return self.user


class FakeDB:
    def __init__(self, user: FakeDbUser | None = None) -> None:
        self.user = user
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        return FakeResult(self.user)


class FakeRedis:
    def __init__(self, *, blacklisted: bool = False, error: Exception | None = None) -> None:
        self.blacklisted = blacklisted
        self.error = error
        self.closed = False

    async def exists(self, key: str) -> bool:
        if self.error:
            raise self.error
        return self.blacklisted

    async def aclose(self) -> None:
        self.closed = True


class FakeRequest:
    cookies: dict[str, str] = {}


def patch_token_and_redis(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, Any] | None = None,
    redis: FakeRedis | None = None,
) -> FakeRedis:
    fake_redis = redis or FakeRedis()
    monkeypatch.setattr(
        deps,
        "decode_token",
        lambda token: payload or {"sub": "7", "username": "alice", "tenant_id": 1},
    )
    monkeypatch.setattr(
        "redis.asyncio.Redis.from_url",
        lambda *args, **kwargs: fake_redis,
    )
    return fake_redis


@pytest.mark.asyncio
async def test_current_user_returns_permissions_role_and_resource_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = patch_token_and_redis(monkeypatch)

    user = await deps.current_user(
        request=object(),  # type: ignore[arg-type]
        token="access-token",
        db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
    )

    assert user["id"] == 7
    assert user["username"] == "alice"
    assert user["display_name"] == "Alice"
    assert user["is_superuser"] is False
    assert user["is_active"] is True
    assert set(user["permissions"]) == {"query:read", "audit:view"}
    assert user["role"] == "engineer"
    assert user["role_id"] == 3
    assert user["manager_id"] == 2
    assert set(user["resource_groups"]) == {10, 20}
    assert user["user_groups"] == [5]
    assert user["tenant_id"] == 1
    assert redis.closed is True


@pytest.mark.asyncio
async def test_current_user_fails_closed_when_redis_blacklist_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_token_and_redis(monkeypatch, redis=FakeRedis(error=RuntimeError("redis down")))

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="access-token",
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "认证服务暂时不可用，请稍后重试"


@pytest.mark.asyncio
async def test_current_user_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=FakeRequest(),  # type: ignore[arg-type]
            token=None,
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "decode_token", lambda token: (_ for _ in ()).throw(PyJWTError()))

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="bad-token",
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_rejects_missing_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "decode_token", lambda token: {"tenant_id": 1})

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="access-token",
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_rejects_inactive_user(monkeypatch: pytest.MonkeyPatch) -> None:
    inactive_user = FakeDbUser()
    inactive_user.is_active = False
    patch_token_and_redis(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="access-token",
            db=FakeDB(inactive_user),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_rejects_blacklisted_token(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_token_and_redis(monkeypatch, redis=FakeRedis(blacklisted=True))

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="access-token",
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_requires_2fa_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_token_and_redis(
        monkeypatch,
        payload={"sub": "7", "username": "alice", "tenant_id": 1, "requires_2fa": True},
    )

    with pytest.raises(HTTPException) as exc:
        await deps.current_user(
            request=object(),  # type: ignore[arg-type]
            token="access-token",
            db=FakeDB(FakeDbUser()),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "请先完成二步验证"


@pytest.mark.asyncio
async def test_current_superuser_and_require_perm_dependencies() -> None:
    superuser = {"is_superuser": True, "permissions": []}
    scoped_user = {"is_superuser": False, "permissions": ["query:read"]}

    assert await deps.current_superuser(superuser) is superuser
    assert await deps.require_perm("query:read")(scoped_user) is scoped_user
    assert await deps.require_perm("any:perm")(superuser) is superuser

    with pytest.raises(HTTPException) as superuser_exc:
        await deps.current_superuser(scoped_user)
    assert superuser_exc.value.status_code == 403

    with pytest.raises(HTTPException) as perm_exc:
        await deps.require_perm("query:write")(scoped_user)
    assert perm_exc.value.status_code == 403
    assert perm_exc.value.detail == "缺少权限：query:write"
