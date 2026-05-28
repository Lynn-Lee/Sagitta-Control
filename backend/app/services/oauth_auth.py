"""
第三方 OAuth2 登录服务。

支持：钉钉（DingTalk）/ 飞书（Feishu）/ 企业微信（WeCom）/ CAS / OIDC。

通用流程：
  1. get_authorize_url(provider, db, callback_url, state) → 平台授权 URL
  2. handle_callback(provider, db, code, callback_url)    → 自动 provision 用户
"""
from __future__ import annotations

import base64
import logging
import urllib.parse
from datetime import UTC, datetime

import httpx
from defusedxml import ElementTree as DefusedET
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import Users
from app.services.system_config import SystemConfigService

logger = logging.getLogger(__name__)

PROVIDER_CONFIG_PROMPTS: dict[str, str] = {
    "dingtalk": "钉钉登录未启用或 AppKey 未配置。",
    "feishu": "飞书登录未启用或 App ID 未配置。",
    "wecom": "企业微信登录未启用或 CorpID / AgentId 未配置。",
    "cas": "CAS 登录未启用或服务器地址未配置。",
    "oidc": "OIDC 登录未启用或 Client ID / Issuer 未配置。",
}


# ── 公共用户 Provision ────────────────────────────────────────

async def _provision_oauth_user(
    db: AsyncSession,
    username: str,
    email: str,
    display_name: str,
    external_id: str,
    auth_type: str,
) -> Users:
    """查找或创建第三方登录用户，自动更新可变属性。"""
    result = await db.execute(
        select(Users).where(
            Users.auth_type == auth_type,
            Users.external_id == external_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        # 兼容首次迁移：按用户名查找
        result = await db.execute(select(Users).where(Users.username == username))
        user = result.scalar_one_or_none()

    if user is None:
        user = Users(
            username=username,
            password=hash_password("__oauth_no_local_password__"),
            display_name=display_name or username,
            email=email or "",
            auth_type=auth_type,
            external_id=external_id,
            is_active=True,
            password_changed_at=datetime.now(UTC),
        )
        db.add(user)
        logger.info("oauth_user_provisioned: provider=%s username=%s", auth_type, username)
    else:
        user.auth_type = auth_type
        user.external_id = external_id
        if display_name:
            user.display_name = display_name
        if email:
            user.email = email

    await db.commit()
    await db.refresh(user)
    return user


# ── 钉钉（DingTalk New API v2）────────────────────────────────

async def get_dingtalk_authorize_url(
    db: AsyncSession, callback_url: str, state: str
) -> str:
    app_id = await SystemConfigService.get_value(db, "ding_login_app_id")
    if not app_id:
        raise ValueError(PROVIDER_CONFIG_PROMPTS["dingtalk"])
    params = {
        "response_type": "code",
        "client_id": app_id,
        "redirect_uri": callback_url,
        "scope": "openid",
        "prompt": "consent",
        "state": state,
    }
    return "https://login.dingtalk.com/oauth2/auth?" + urllib.parse.urlencode(params)


async def handle_dingtalk_callback(
    db: AsyncSession, code: str, callback_url: str
) -> Users:
    app_id = await SystemConfigService.get_value(db, "ding_login_app_id")
    app_secret = await SystemConfigService.get_value(db, "ding_login_app_secret")
    if not app_id or not app_secret:
        raise ValueError("钉钉登录配置不完整")

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
            json={
                "clientId": app_id,
                "clientSecret": app_secret,
                "code": code,
                "grantType": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("accessToken")
        if not access_token:
            raise ValueError(f"钉钉获取 Token 失败: {token_data}")

        me_resp = await client.get(
            "https://api.dingtalk.com/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": access_token},
        )
        me_resp.raise_for_status()
        user_info = me_resp.json()

    union_id = user_info.get("unionId", "")
    nick = user_info.get("nick", "")
    email = user_info.get("email", "")
    username = f"ding_{union_id[:12]}" if union_id else f"ding_{nick}"
    return await _provision_oauth_user(db, username, email, nick, union_id, "dingtalk")


# ── 飞书（Feishu / Lark）─────────────────────────────────────

async def get_feishu_authorize_url(
    db: AsyncSession, callback_url: str, state: str
) -> str:
    app_id = await SystemConfigService.get_value(db, "feishu_app_id")
    if not app_id:
        raise ValueError(PROVIDER_CONFIG_PROMPTS["feishu"])
    params = {
        "app_id": app_id,
        "redirect_uri": callback_url,
        "scope": "contact:user.base:readonly",
        "state": state,
    }
    return "https://accounts.feishu.cn/open-apis/authen/v1/authorize?" + urllib.parse.urlencode(params)


async def handle_feishu_callback(
    db: AsyncSession, code: str, callback_url: str
) -> Users:
    app_id = await SystemConfigService.get_value(db, "feishu_app_id")
    app_secret = await SystemConfigService.get_value(db, "feishu_app_secret")
    if not app_id or not app_secret:
        raise ValueError("飞书登录配置不完整")

    creds = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/json",
            },
            json={"grant_type": "authorization_code", "code": code},
        )
        token_resp.raise_for_status()
        token_body = token_resp.json()
        if token_body.get("code") != 0:
            raise ValueError(f"飞书获取 Token 失败: {token_body.get('msg')}")
        access_token = token_body["data"]["access_token"]

        me_resp = await client.get(
            "https://open.feishu.cn/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        me_resp.raise_for_status()
        me_body = me_resp.json()
        if me_body.get("code") != 0:
            raise ValueError(f"飞书获取用户信息失败: {me_body.get('msg')}")
        user_data = me_body["data"]

    open_id = user_data.get("open_id", "")
    name = user_data.get("name", "")
    email = user_data.get("email", "")
    username = f"feishu_{open_id[:12]}" if open_id else f"feishu_{name}"
    return await _provision_oauth_user(db, username, email, name, open_id, "feishu")


# ── 企业微信（WeCom）──────────────────────────────────────────

async def get_wecom_authorize_url(
    db: AsyncSession, callback_url: str, state: str
) -> str:
    corp_id = await SystemConfigService.get_value(db, "wecom_login_corp_id")
    agent_id = await SystemConfigService.get_value(db, "wecom_login_agent_id")
    if not corp_id or not agent_id:
        raise ValueError(PROVIDER_CONFIG_PROMPTS["wecom"])
    params = {
        "appid": corp_id,
        "agentid": agent_id,
        "redirect_uri": callback_url,
        "state": state,
    }
    return "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?" + urllib.parse.urlencode(params)


async def handle_wecom_callback(
    db: AsyncSession, code: str, callback_url: str
) -> Users:
    corp_id = await SystemConfigService.get_value(db, "wecom_login_corp_id")
    app_secret = await SystemConfigService.get_value(db, "wecom_login_app_secret")
    if not corp_id or not app_secret:
        raise ValueError("企业微信登录配置不完整")

    async with httpx.AsyncClient(timeout=10) as client:
        # 第 1 步：获取企业级 access token
        token_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": app_secret},
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        if token_data.get("errcode", 0) != 0:
            raise ValueError(f"企微获取 Token 失败: {token_data.get('errmsg')}")
        access_token = token_data["access_token"]

        # 第 2 步：code → UserId
        uid_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
            params={"access_token": access_token, "code": code},
        )
        uid_resp.raise_for_status()
        uid_data = uid_resp.json()
        if uid_data.get("errcode", 0) != 0:
            raise ValueError(f"企微获取用户身份失败: {uid_data.get('errmsg')}")
        user_id = uid_data.get("UserId") or uid_data.get("OpenId", "")

        # 第 3 步：获取用户详情（仅 UserId 情况下有完整信息）
        name = ""
        email = ""
        if uid_data.get("UserId"):
            detail_resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/user/get",
                params={"access_token": access_token, "userid": user_id},
            )
            detail_resp.raise_for_status()
            detail = detail_resp.json()
            if detail.get("errcode", 0) == 0:
                name = detail.get("name", "")
                email = detail.get("email", "") or detail.get("biz_mail", "")

    username = f"wecom_{user_id[:12]}" if user_id else "wecom_user"
    return await _provision_oauth_user(db, username, email, name, user_id, "wecom")


# ── CAS（Central Authentication Service）────────────────────

def _normalize_cas_server_url(raw_url: str) -> str:
    """返回 CAS 基础 URL，并兼容管理员常填的端点 URL。"""
    url = raw_url.strip().rstrip("/")
    for suffix in (
        "/p3/serviceValidate",
        "/serviceValidate",
        "/p3/proxyValidate",
        "/proxyValidate",
        "/login",
    ):
        if url.lower().endswith(suffix.lower()):
            url = url[: -len(suffix)].rstrip("/")
            break
    return url


async def get_cas_authorize_url(
    db: AsyncSession, callback_url: str, state: str
) -> str:
    cas_server_url = await SystemConfigService.get_value(db, "cas_server_url")
    if not cas_server_url:
        raise ValueError(PROVIDER_CONFIG_PROMPTS["cas"])
    cas_base_url = _normalize_cas_server_url(cas_server_url)
    if not cas_base_url:
        raise ValueError("CAS 服务器地址格式不正确")
    # 将 state 嵌入 service URL，CAS 会原样回传
    service = callback_url + "?" + urllib.parse.urlencode({"state": state})
    return cas_base_url + "/login?" + urllib.parse.urlencode({"service": service})


async def get_cas_logout_url(db: AsyncSession, redirect_url: str) -> str:
    cas_server_url = await SystemConfigService.get_value(db, "cas_server_url")
    if not cas_server_url:
        raise ValueError("CAS 服务器地址未配置，请在系统配置 → CAS 单点登录中填写")
    cas_base_url = _normalize_cas_server_url(cas_server_url)
    if not cas_base_url:
        raise ValueError("CAS 服务器地址格式不正确")
    return cas_base_url + "/logout?" + urllib.parse.urlencode({"service": redirect_url})


async def handle_cas_callback(
    db: AsyncSession, ticket: str, callback_url: str
) -> Users:
    """callback_url 须与 authorize 时完全一致（含 state 参数）。"""
    cas_server_url = await SystemConfigService.get_value(db, "cas_server_url")
    username_attr = await SystemConfigService.get_value(db, "cas_username_attribute") or "user"
    if not cas_server_url:
        raise ValueError("CAS 配置不完整（服务器地址缺失）")
    cas_base_url = _normalize_cas_server_url(cas_server_url)
    if not cas_base_url:
        raise ValueError("CAS 服务器地址格式不正确")

    validate_url = cas_base_url + "/serviceValidate"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(validate_url, params={"service": callback_url, "ticket": ticket})
        resp.raise_for_status()
        xml_text = resp.text

    root = DefusedET.fromstring(xml_text)
    ns = {"cas": "http://www.yale.edu/tp/cas"}

    success = root.find("cas:authenticationSuccess", ns)
    if success is None:
        failure = root.find("cas:authenticationFailure", ns)
        msg = (failure.text or "票据验证失败").strip() if failure is not None else "票据验证失败"
        raise ValueError(f"CAS 认证失败: {msg}")

    user_elem = success.find("cas:user", ns)
    username = (user_elem.text or "").strip() if user_elem is not None else ""
    if not username:
        raise ValueError("CAS 未返回用户名")

    attrs_elem = success.find("cas:attributes", ns)
    email = ""
    display_name = ""
    if attrs_elem is not None:
        for tag in ("cas:email", f"cas:{username_attr}"):
            elem = attrs_elem.find(tag, ns)
            if elem is not None and elem.text:
                email = elem.text.strip()
                break
        for tag in ("cas:displayName", "cas:cn", "cas:name"):
            elem = attrs_elem.find(tag, ns)
            if elem is not None and elem.text:
                display_name = elem.text.strip()
                break

    return await _provision_oauth_user(db, username, email, display_name or username, username, "cas")


# ── OIDC（OpenID Connect）───────────────────────────────────

def _normalize_oidc_issuer_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    suffix = "/.well-known/openid-configuration"
    if url.lower().endswith(suffix):
        url = url[: -len(suffix)].rstrip("/")
    return url


async def _get_oidc_metadata(db: AsyncSession) -> dict[str, str]:
    issuer_url = _normalize_oidc_issuer_url(
        await SystemConfigService.get_value(db, "oidc_issuer_url")
    )
    metadata: dict[str, str] = {}
    if issuer_url:
        discovery_url = issuer_url + "/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(discovery_url)
                resp.raise_for_status()
                body = resp.json()
            metadata = {
                "authorization_endpoint": body.get("authorization_endpoint", ""),
                "token_endpoint": body.get("token_endpoint", ""),
                "userinfo_endpoint": body.get("userinfo_endpoint", ""),
            }
        except Exception as exc:
            logger.warning("oidc_discovery_failed: issuer=%s error=%s", issuer_url, exc)

    overrides = {
        "authorization_endpoint": await SystemConfigService.get_value(
            db, "oidc_authorization_endpoint"
        ),
        "token_endpoint": await SystemConfigService.get_value(db, "oidc_token_endpoint"),
        "userinfo_endpoint": await SystemConfigService.get_value(db, "oidc_userinfo_endpoint"),
    }
    for key, value in overrides.items():
        if value:
            metadata[key] = value.strip()
    return metadata


async def get_oidc_authorize_url(
    db: AsyncSession, callback_url: str, state: str
) -> str:
    client_id = await SystemConfigService.get_value(db, "oidc_client_id")
    metadata = await _get_oidc_metadata(db)
    authorize_endpoint = metadata.get("authorization_endpoint", "")
    if not client_id or not authorize_endpoint:
        raise ValueError(PROVIDER_CONFIG_PROMPTS["oidc"])

    scope = await SystemConfigService.get_value(db, "oidc_scope") or "openid email profile"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_url,
        "scope": scope,
        "state": state,
    }
    return authorize_endpoint + "?" + urllib.parse.urlencode(params)


async def handle_oidc_callback(
    db: AsyncSession, code: str, callback_url: str
) -> Users:
    client_id = await SystemConfigService.get_value(db, "oidc_client_id")
    client_secret = await SystemConfigService.get_value(db, "oidc_client_secret")
    metadata = await _get_oidc_metadata(db)
    token_endpoint = metadata.get("token_endpoint", "")
    userinfo_endpoint = metadata.get("userinfo_endpoint", "")
    if not client_id or not token_endpoint or not userinfo_endpoint:
        raise ValueError("OIDC 登录配置不完整")

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url,
        "client_id": client_id,
    }
    if client_secret:
        token_payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(token_endpoint, data=token_payload)
        if token_resp.status_code in (400, 401) and client_secret:
            token_payload.pop("client_secret", None)
            token_resp = await client.post(
                token_endpoint,
                data=token_payload,
                auth=(client_id, client_secret),
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(f"OIDC 获取 Token 失败: {token_data}")

        userinfo_resp = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_resp.raise_for_status()
        user_data = userinfo_resp.json()

    sub = str(user_data.get("sub") or "")
    username_claim = await SystemConfigService.get_value(db, "oidc_username_claim")
    email_claim = await SystemConfigService.get_value(db, "oidc_email_claim")
    display_claim = await SystemConfigService.get_value(db, "oidc_display_name_claim")

    email = str(user_data.get(email_claim or "email") or "")
    display_name = str(user_data.get(display_claim or "name") or "")
    username = str(
        user_data.get(username_claim or "preferred_username")
        or email.split("@")[0]
        or (f"oidc_{sub[:12]}" if sub else "")
    )
    username = username.strip().replace(" ", "_")
    external_id = sub or username
    if not username or not external_id:
        raise ValueError("OIDC 未返回可识别的用户标识")

    return await _provision_oauth_user(
        db, username, email, display_name or username, external_id, "oidc"
    )


# ── 统一分发入口 ──────────────────────────────────────────────

SUPPORTED_PROVIDERS = ("dingtalk", "feishu", "wecom", "cas", "oidc")

_PROVIDER_ENABLED_KEY: dict[str, str] = {
    "dingtalk": "ding_login_enabled",
    "feishu":   "feishu_login_enabled",
    "wecom":    "wecom_login_enabled",
    "cas":      "cas_enabled",
    "oidc":     "oidc_enabled",
}

_GET_URL = {
    "dingtalk": get_dingtalk_authorize_url,
    "feishu":   get_feishu_authorize_url,
    "wecom":    get_wecom_authorize_url,
    "cas":      get_cas_authorize_url,
    "oidc":     get_oidc_authorize_url,
}

_HANDLE_CB = {
    "dingtalk": handle_dingtalk_callback,
    "feishu":   handle_feishu_callback,
    "wecom":    handle_wecom_callback,
    "cas":      handle_cas_callback,
    "oidc":     handle_oidc_callback,
}


async def get_authorize_url(
    provider: str, db: AsyncSession, callback_url: str, state: str
) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的登录方式: {provider}")
    enabled_key = _PROVIDER_ENABLED_KEY[provider]
    enabled = await SystemConfigService.get_value(db, enabled_key)
    if enabled.lower() != "true":
        raise ValueError(PROVIDER_CONFIG_PROMPTS[provider])
    return await _GET_URL[provider](db, callback_url, state)


async def handle_callback(
    provider: str, db: AsyncSession, code: str, callback_url: str
) -> Users:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的登录方式: {provider}")
    return await _HANDLE_CB[provider](db, code, callback_url)
