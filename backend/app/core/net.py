"""客户端网络信息解析。

审计与查询日志需要记录真实客户端 IP。X-Forwarded-For 由客户端可控，
最左侧条目可被伪造；每经过一层可信代理会在右侧追加其看到的对端 IP，
因此真实客户端 IP 应从右往左第 `TRUSTED_PROXY_COUNT` 个条目取值。
"""
from __future__ import annotations

from fastapi import Request

from app.core.config import settings


def resolve_client_ip(request: Request) -> str:
    """还原真实客户端 IP。

    - `TRUSTED_PROXY_COUNT <= 0`：无前置代理，直接使用 socket 对端地址，忽略 XFF。
    - 否则取 X-Forwarded-For 从右往左第 N（N=可信代理层数）个条目，即最外层可信
      代理注入的地址；条目数不足（异常或直连伪造）时回退到 socket 对端地址。
    """
    peer = request.client.host if request.client else ""
    hops = settings.TRUSTED_PROXY_COUNT
    if hops <= 0:
        return peer

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return peer
    entries = [item.strip() for item in forwarded.split(",") if item.strip()]
    if len(entries) < hops:
        # XFF 条目比可信跳数少：请求未按预期经过全部可信代理，最左侧条目不可信，回退对端地址
        return peer
    return entries[-hops]
