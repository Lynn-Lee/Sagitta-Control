"""客户端 IP 解析（可信代理还原）单元测试。"""
from types import SimpleNamespace

import pytest

from app.core import net


def _request(xff: str | None, peer: str = "203.0.113.9"):
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=peer) if peer is not None else None,
    )


@pytest.fixture(autouse=True)
def _reset_hops(monkeypatch):
    monkeypatch.setattr(net.settings, "TRUSTED_PROXY_COUNT", 1)


def test_single_proxy_takes_proxy_injected_rightmost_entry():
    # 客户端伪造最左侧 IP，nginx 追加真实对端；应取右侧可信条目而非伪造值
    req = _request("1.2.3.4, 100.64.0.5")
    assert net.resolve_client_ip(req) == "100.64.0.5"


def test_single_proxy_plain_forward():
    req = _request("198.51.100.7")
    assert net.resolve_client_ip(req) == "198.51.100.7"


def test_two_trusted_hops(monkeypatch):
    monkeypatch.setattr(net.settings, "TRUSTED_PROXY_COUNT", 2)
    # [client, lb, ]nginx 追加 -> XFF = client, lb ；真实客户端为从右第 2 个
    req = _request("9.9.9.9, 10.0.0.2, 10.0.0.3")
    assert net.resolve_client_ip(req) == "10.0.0.2"


def test_no_proxy_ignores_forwarded_header(monkeypatch):
    monkeypatch.setattr(net.settings, "TRUSTED_PROXY_COUNT", 0)
    req = _request("1.2.3.4", peer="203.0.113.9")
    assert net.resolve_client_ip(req) == "203.0.113.9"


def test_fewer_entries_than_hops_falls_back_to_peer(monkeypatch):
    monkeypatch.setattr(net.settings, "TRUSTED_PROXY_COUNT", 2)
    # 只有 1 个条目但配置 2 层可信代理：未按预期经过全部代理，回退 socket 对端
    req = _request("1.2.3.4", peer="203.0.113.9")
    assert net.resolve_client_ip(req) == "203.0.113.9"


def test_missing_forwarded_header_uses_peer():
    req = _request(None, peer="203.0.113.9")
    assert net.resolve_client_ip(req) == "203.0.113.9"


def test_no_client_and_no_header_returns_empty():
    req = _request(None, peer=None)
    assert net.resolve_client_ip(req) == ""
