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
        "oidc_enabled":             "true",
        "oidc_client_id":           "oidc_client",
        "oidc_client_secret":       "oidc_secret",
        "oidc_authorization_endpoint": "https://idp.example.com/oauth2/authorize",
        "oidc_token_endpoint":      "https://idp.example.com/oauth2/token",
        "oidc_userinfo_endpoint":   "https://idp.example.com/oauth2/userinfo",
        "oidc_scope":               "openid email profile",
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
        pytest.raises(ValueError, match="钉钉登录未启用或 AppKey 未配置。"),
    ):
        await oauth_auth.get_authorize_url("dingtalk", mock_db, "http://cb", "state")


@pytest.mark.asyncio
async def test_get_authorize_url_disabled_uses_enterprise_prompt(mock_db):
    cfg = _make_config(
        feishu_login_enabled="false",
        wecom_login_enabled="false",
        cas_enabled="false",
        oidc_enabled="false",
    )
    with (
        patch("app.services.oauth_auth.SystemConfigService.get_value",
              side_effect=await _mock_get_value(cfg)),
        pytest.raises(ValueError, match="飞书登录未启用或 App ID 未配置。"),
    ):
        await oauth_auth.get_authorize_url("feishu", mock_db, "http://cb", "state")

    with (
        patch("app.services.oauth_auth.SystemConfigService.get_value",
              side_effect=await _mock_get_value(cfg)),
        pytest.raises(ValueError, match="企业微信登录未启用或 CorpID / AgentId 未配置。"),
    ):
        await oauth_auth.get_authorize_url("wecom", mock_db, "http://cb", "state")

    with (
        patch("app.services.oauth_auth.SystemConfigService.get_value",
              side_effect=await _mock_get_value(cfg)),
        pytest.raises(ValueError, match="CAS 登录未启用或服务器地址未配置。"),
    ):
        await oauth_auth.get_authorize_url("cas", mock_db, "http://cb", "state")

    with (
        patch("app.services.oauth_auth.SystemConfigService.get_value",
              side_effect=await _mock_get_value(cfg)),
        pytest.raises(ValueError, match="OIDC 登录未启用或 Client ID / Issuer 未配置。"),
    ):
        await oauth_auth.get_authorize_url("oidc", mock_db, "http://cb", "state")


@pytest.mark.asyncio
async def test_missing_provider_config_uses_enterprise_prompt(mock_db):
    cfg = _make_config(
        ding_login_app_id="",
        feishu_app_id="",
        wecom_login_corp_id="",
        cas_enabled="true",
        cas_server_url="",
        oidc_client_id="",
    )
    expected = {
        "dingtalk": "钉钉登录未启用或 AppKey 未配置。",
        "feishu": "飞书登录未启用或 App ID 未配置。",
        "wecom": "企业微信登录未启用或 CorpID / AgentId 未配置。",
        "cas": "CAS 登录未启用或服务器地址未配置。",
        "oidc": "OIDC 登录未启用或 Client ID / Issuer 未配置。",
    }
    for provider, message in expected.items():
        with (
            patch("app.services.oauth_auth.SystemConfigService.get_value",
                  side_effect=await _mock_get_value(cfg)),
            pytest.raises(ValueError, match=message),
        ):
            await oauth_auth.get_authorize_url(provider, mock_db, "http://cb", "state")


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


@pytest.mark.asyncio
async def test_oidc_authorize_url_uses_configured_endpoint(mock_db):
    cfg = _make_config()
    with patch("app.services.oauth_auth.SystemConfigService.get_value",
               side_effect=await _mock_get_value(cfg)):
        url = await oauth_auth.get_authorize_url(
            "oidc", mock_db, "https://db.example.com/api/v1/auth/oidc/callback/", "st6"
        )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.geturl().startswith("https://idp.example.com/oauth2/authorize?")
    assert query["client_id"] == ["oidc_client"]
    assert query["redirect_uri"] == ["https://db.example.com/api/v1/auth/oidc/callback/"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] == ["st6"]
