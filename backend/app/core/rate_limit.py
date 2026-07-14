"""基于 Redis 有序集合的滑动窗口限速（用于认证入口，防口令喷洒/短信轰炸/TOTP 猜测）。

限速对 Redis 不可用采取 fail-open：Redis 异常时放行请求，避免因缓存故障阻断全部登录，
认证入口的其它防线（密码校验、TOTP、账号锁定策略）仍然生效。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import Request

from app.core.exceptions import AppException
from app.core.net import resolve_client_ip

logger = logging.getLogger(__name__)


async def _sliding_window_allow(
    redis: Any, key: str, limit: int, window_seconds: int
) -> bool:
    """滑动窗口计数：本次请求计入后若总数 <= limit 返回 True。"""
    now = time.time()
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds)
    _, _, count, _ = await pipe.execute()
    return int(count) <= limit


async def enforce_rate_limit(
    redis: Any,
    key: str,
    *,
    limit: int,
    window_seconds: int,
    error_msg: str,
) -> None:
    """超过阈值抛出 429；Redis 故障时 fail-open 放行。"""
    try:
        allowed = await _sliding_window_allow(redis, key, limit, window_seconds)
    except Exception as exc:  # pragma: no cover - 依赖 Redis 运行态
        logger.warning("rate_limit check failed, fail-open: key=%s error=%s", key, str(exc))
        return
    if not allowed:
        raise AppException(error_msg, code=429)


async def enforce_auth_rate_limit(
    redis: Any,
    request: Request,
    identifier: str | None,
    *,
    scope: str = "login",
    ip_limit: int = 20,
    ip_window: int = 60,
    id_limit: int = 10,
    id_window: int = 300,
) -> None:
    """认证入口双维度限速：按来源 IP 与 按账号标识分别限流。"""
    ip = resolve_client_ip(request) or "unknown"
    await enforce_rate_limit(
        redis,
        f"rl:{scope}:ip:{ip}",
        limit=ip_limit,
        window_seconds=ip_window,
        error_msg="请求过于频繁，请稍后再试",
    )
    if identifier:
        await enforce_rate_limit(
            redis,
            f"rl:{scope}:id:{identifier}",
            limit=id_limit,
            window_seconds=id_window,
            error_msg="尝试次数过多，请稍后再试",
        )
