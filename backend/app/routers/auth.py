"""
认证路由：本地登录、LDAP、第三方 OAuth2（钉钉/飞书/企微/CAS）、2FA、Token 管理。
"""

import logging
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import quote as urllib_quote
from urllib.parse import urlencode as urllib_urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, oauth2_scheme
from app.core.security import (
    create_access_token,
    create_password_change_token,
    create_refresh_token,
    decode_token,
    decrypt_field,
    encrypt_field,
    get_login_password_change_reasons,
    get_password_days_until_expiry,
    hash_password,
    is_password_expiring_soon,
    verify_password,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ForceChangePasswordRequest,
    LdapLoginRequest,
    LoginRequest,
    RefreshRequest,
    SmsCodeRequest,
    SmsLoginRequest,
    TokenResponse,
    TwoFAVerifyRequest,
)
from app.services import oauth_auth
from app.services.ldap_auth import LdapAuthService
from app.services.system_config import SystemConfigService
from app.services.user import UserService

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_redis():
    from redis.asyncio import Redis

    from app.core.config import settings

    r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


@router.post("/login/", response_model=TokenResponse, summary="用户名密码登录")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await UserService.get_by_username(db, data.username)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    password_change_reasons = get_login_password_change_reasons(
        data.password,
        user.password_changed_at,
    )
    if password_change_reasons:
        logger.info("user_login_password_change_required: %s", user.username)
        return TokenResponse(
            password_change_required=True,
            password_change_token=create_password_change_token(
                {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
            ),
            password_change_reasons=password_change_reasons,
        )

    payload = {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
    if user.totp_enabled:
        payload["requires_2fa"] = True

    logger.info("user_login")
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token({"sub": str(user.id), "tenant_id": user.tenant_id}),
    )


@router.post("/login/form/", response_model=TokenResponse, include_in_schema=False)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    return await login(LoginRequest(username=form_data.username, password=form_data.password), db)


@router.post("/ldap/", response_model=TokenResponse, summary="LDAP 登录")
async def ldap_login(data: LdapLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await LdapAuthService.authenticate(db, data.username, data.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    payload = {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
    logger.info("ldap_user_login: %s", user.username)
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token({"sub": str(user.id), "tenant_id": user.tenant_id}),
    )


@router.post("/token/refresh/", response_model=TokenResponse, summary="刷新 access_token")
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期") from e
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="非法的 token 类型")

    user = await UserService.get_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    new_payload = {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
    if user.totp_enabled:
        new_payload["requires_2fa"] = True
    return TokenResponse(
        access_token=create_access_token(new_payload),
        refresh_token=create_refresh_token({"sub": str(user.id), "tenant_id": user.tenant_id}),
    )


@router.post("/logout/", summary="登出")
async def logout(token: str = Depends(oauth2_scheme), redis=Depends(get_redis)):
    try:
        payload = decode_token(token)
        ttl = int(payload.get("exp", 0)) - int(time.time())
        if ttl > 0:
            await redis.setex(f"blacklist:{token}", ttl, "1")
    except JWTError:
        pass
    return {"status": 0, "msg": "已退出登录"}


@router.post("/2fa/setup/", summary="生成 TOTP 密钥")
async def setup_2fa(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    import pyotp

    db_user = await UserService.get_by_id(db, user["id"])
    if not db_user:
        raise HTTPException(404, "用户不存在")
    secret = pyotp.random_base32()
    db_user.totp_secret = encrypt_field(secret)
    await db.commit()
    totp = pyotp.TOTP(secret)
    return {
        "secret": secret,
        "provisioning_uri": totp.provisioning_uri(name=db_user.username, issuer_name="SagittaDB"),
    }


@router.post("/2fa/verify/", summary="验证 TOTP 并激活 2FA")
async def verify_2fa(
    data: TwoFAVerifyRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)
):
    import pyotp

    db_user = await UserService.get_by_id(db, user["id"])
    if not db_user or not db_user.totp_secret:
        raise HTTPException(400, "请先调用 /2fa/setup/ 生成密钥")
    secret = decrypt_field(db_user.totp_secret)
    if not pyotp.TOTP(secret).verify(data.totp_code, valid_window=1):
        raise HTTPException(400, "TOTP 验证码错误")
    db_user.totp_enabled = True
    await db.commit()
    return {"status": 0, "msg": "2FA 已启用"}


@router.post("/2fa/disable/", summary="禁用 2FA")
async def disable_2fa(
    data: TwoFAVerifyRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)
):
    import pyotp

    db_user = await UserService.get_by_id(db, user["id"])
    if not db_user or not db_user.totp_enabled:
        raise HTTPException(400, "2FA 未启用")
    secret = decrypt_field(db_user.totp_secret)
    if not pyotp.TOTP(secret).verify(data.totp_code, valid_window=1):
        raise HTTPException(400, "TOTP 验证码错误")
    db_user.totp_enabled = False
    db_user.totp_secret = None
    await db.commit()
    return {"status": 0, "msg": "2FA 已禁用"}


@router.get("/me/", summary="获取当前用户信息")
async def get_me(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    db_user = await UserService.get_by_id(db, user["id"])
    if not db_user:
        raise HTTPException(404, "用户不存在")
    # v2: permissions from current_user already merges role + direct perms
    return {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name,
        "email": db_user.email,
        "is_superuser": db_user.is_superuser,
        "is_active": db_user.is_active,
        "auth_type": db_user.auth_type,
        "totp_enabled": db_user.totp_enabled,
        "permissions": user.get("permissions", []),
        "role": db_user.role.name if db_user.role else None,
        "role_id": db_user.role_id,
        "manager_id": db_user.manager_id,
        "employee_id": db_user.employee_id,
        "department": db_user.department,
        "title": db_user.title,
        "resource_groups": user.get("resource_groups", []),
        "user_groups": user.get("user_groups", []),
        "tenant_id": db_user.tenant_id,
        "password_expiring_soon": is_password_expiring_soon(db_user.password_changed_at),
        "days_until_password_expiry": get_password_days_until_expiry(db_user.password_changed_at),
    }


@router.post("/password/change/", summary="修改密码")
async def change_password(
    data: ChangePasswordRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)
):
    await UserService.change_password(db, user["id"], data.old_password, data.new_password)
    return {"status": 0, "msg": "密码已修改，请重新登录"}


@router.post("/password/change-required/", summary="强制修改密码")
async def force_change_password(data: ForceChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.password_change_token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail="改密凭证无效或已过期") from e
    if payload.get("type") != "password_change":
        raise HTTPException(status_code=401, detail="非法的改密凭证")

    user = await UserService.get_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    user.password = hash_password(data.new_password)
    user.password_changed_at = datetime.now(UTC)
    await db.commit()
    return {"status": 0, "msg": "密码已修改，请使用新密码重新登录"}


# ── 短信验证码登录（v2）──────────────────────────────────────────


@router.post("/sms/send/", summary="发送短信验证码")
async def sms_send_code(data: SmsCodeRequest, db: AsyncSession = Depends(get_db)):
    """向指定手机号发送验证码（受频率限制）。"""
    from app.services.sms_auth import send_sms_code

    result = await send_sms_code(db, data.phone)
    return result


@router.post("/sms/login/", response_model=TokenResponse, summary="短信验证码登录")
async def sms_login(data: SmsLoginRequest, db: AsyncSession = Depends(get_db)):
    """用手机号 + 验证码登录。验证码一次性使用，验证成功后自动删除。"""
    from app.services.sms_auth import verify_sms_code
    from app.services.user import UserService

    if not await verify_sms_code(data.phone, data.code):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")

    user = await UserService.get_by_phone(db, data.phone)
    if not user:
        raise HTTPException(status_code=404, detail="该手机号未关联任何账号")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    payload = {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
    logger.info("sms_login: %s", user.username)
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token({"sub": str(user.id), "tenant_id": user.tenant_id}),
    )


# ── 第三方 OAuth2 登录（Pack F）──────────────────────────────


@router.get("/{provider}/authorize/", summary="获取第三方登录授权 URL")
async def oauth_authorize(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    返回指定 provider 的授权跳转 URL。
    支持：dingtalk / feishu / wecom / cas
    """
    if provider not in oauth_auth.SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"不支持的登录方式: {provider}")

    state = str(uuid.uuid4())
    await redis.setex(f"oauth_state:{state}", 300, provider)

    # 回调 URL 指向本后端 callback 端点
    callback_url = str(request.base_url).rstrip("/") + f"/api/v1/auth/{provider}/callback/"

    try:
        url = await oauth_auth.get_authorize_url(provider, db, callback_url, state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"url": url, "state": state}


@router.get(
    "/{provider}/callback/", summary="第三方登录回调（由平台跳回）", include_in_schema=False
)
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    code: str | None = None,
    ticket: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """
    接收平台 OAuth2 回调，验证 state、换取用户信息，生成 JWT 后重定向到前端。
    成功：→ {platform_url}/oauth/callback?access_token=...&refresh_token=...
    失败：→ {platform_url}/login?oauth_error=...
    """
    platform_url = (await SystemConfigService.get_value(db, "platform_url")).rstrip("/")
    if not platform_url:
        platform_url = "http://localhost"

    def _redirect_error(msg: str) -> RedirectResponse:
        return RedirectResponse(
            f"{platform_url}/login?oauth_error={urllib_quote(msg)}", status_code=302
        )

    if error:
        return _redirect_error(f"用户取消或平台返回错误: {error}")

    # CAS 使用 ticket 参数，OAuth2 使用 code 参数
    auth_code = code or ticket
    if not auth_code or not state:
        return _redirect_error("回调参数缺失")

    # 验证 CSRF state
    stored_provider = await redis.get(f"oauth_state:{state}")
    if not stored_provider or stored_provider != provider:
        return _redirect_error("state 验证失败，请重新登录")
    await redis.delete(f"oauth_state:{state}")

    base_callback = str(request.base_url).rstrip("/") + f"/api/v1/auth/{provider}/callback/"
    # CAS 校验须与 authorize 时完全一致的 service URL（含 state 参数）
    callback_url = (
        base_callback + "?" + urllib_urlencode({"state": state})
        if provider == "cas"
        else base_callback
    )

    try:
        user = await oauth_auth.handle_callback(provider, db, auth_code, callback_url)
    except Exception as e:
        logger.warning("oauth_callback_error: provider=%s error=%s", provider, str(e))
        return _redirect_error(str(e))

    if not user.is_active:
        return _redirect_error("账号已被禁用，请联系管理员")

    payload = {"sub": str(user.id), "username": user.username, "tenant_id": user.tenant_id}
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token({"sub": str(user.id), "tenant_id": user.tenant_id})

    logger.info("oauth_login: provider=%s username=%s", provider, user.username)
    return RedirectResponse(
        f"{platform_url}/oauth/callback?access_token={access_token}&refresh_token={refresh_token}",
        status_code=302,
    )
