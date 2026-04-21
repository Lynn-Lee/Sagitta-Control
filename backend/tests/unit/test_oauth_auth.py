"""
OAuth2 认证服务单元测试（验证配置校验逻辑，使用 mock）。
"""
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app.services import oauth_auth


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_config(**overrides):
    base = {
        "ding_login_enabled":       "true",
        "ding_login_app_id":        "test_app_id",
        "ding_login_app_secret":    "test_secret",
        "feishu_login_enabled":     "true",
        "feishu_app_id":            "cli_xxx",
        "feishu_app_secret":        "secret",
        "wecom_login_enabled":      "true",
        "wecom_login_corp_id":      "wx_corp",
        "wecom_login_agent_id":     "1000001",
        "wecom_login_app_secret":   "corp_secret",
    }
    base.update(overrides)
    return base


async def _mock_get_value(cfg: dict):
    async def _impl(db, key):
        return cfg.get(key, "")
    return _impl


# ── get_authorize_url ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_authorize_url_unsupported_provider(mock_db):
    with pytest.raises(ValueError, match="不支持"):
        await oauth_auth.get_authorize_url("github", mock_db, "http://cb", "state")


@pytest.mark.asyncio
async def test_get_authorize_url_disabled(mock_db):
    cfg = _make_config(ding_login_enabled="false")
    with (
        patch("app.services.oauth_auth.SystemConfigService.get_value",
              side_effect=await _mock_get_value(cfg)),
        pytest.raises(ValueError, match="未启用"),
    ):
        await oauth_auth.get_authorize_url("dingtalk", mock_db, "http://cb", "state")


@pytest.mark.asyncio
async def test_dingtalk_authorize_url_contains_client_id(mock_db):
    cfg = _make_config()
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url("dingtalk", mock_db, "http://cb", "st1")
    assert "login.dingtalk.com" in url
    assert "test_app_id" in url
    assert "st1" in url


@pytest.mark.asyncio
async def test_feishu_authorize_url(mock_db):
    cfg = _make_config()
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url("feishu", mock_db, "http://cb", "st2")
    assert "feishu.cn" in url
    assert "cli_xxx" in url


@pytest.mark.asyncio
async def test_wecom_authorize_url(mock_db):
    cfg = _make_config()
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url("wecom", mock_db, "http://cb", "st3")
    assert "work.weixin.qq.com" in url
    assert "wx_corp" in url


@pytest.mark.asyncio
async def test_cas_authorize_url_uses_base_url(mock_db):
    cfg = _make_config(cas_enabled="true", cas_server_url="https://cas.example.com")
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url(
            "cas", mock_db, "https://db.example.com/api/v1/auth/cas/callback/", "st4"
        )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.geturl().startswith("https://cas.example.com/login?")
    assert query["service"] == ["https://db.example.com/api/v1/auth/cas/callback/?state=st4"]


@pytest.mark.asyncio
async def test_cas_authorize_url_normalizes_login_endpoint(mock_db):
    cfg = _make_config(cas_enabled="true", cas_server_url="https://cas.example.com/login")
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url(
            "cas", mock_db, "https://db.example.com/api/v1/auth/cas/callback/", "st5"
        )
    assert url.startswith("https://cas.example.com/login?")
    assert "/login/login?" not in url
