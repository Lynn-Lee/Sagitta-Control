"""浏览器 Cookie 登录态与 CSRF 双提交校验。"""

import secrets
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.schemas.auth import TokenResponse

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login/",
    "/api/v1/auth/login/form/",
    "/api/v1/auth/ldap/",
    "/api/v1/auth/sms/login/",
    "/api/v1/auth/2fa/login/verify/",
    "/api/v1/auth/password/change-required/",
    "/api/v1/auth/oauth/exchange/",
}


def _cookie_kwargs(*, max_age: int, httponly: bool) -> dict[str, Any]:
    return {
        "path": "/",
        "max_age": max_age,
        "httponly": httponly,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN or None,
    }


def set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    if not tokens.access_token or not tokens.refresh_token:
        return

    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        tokens.access_token,
        **_cookie_kwargs(max_age=access_max_age, httponly=True),
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        **_cookie_kwargs(max_age=refresh_max_age, httponly=True),
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(32),
        **_cookie_kwargs(max_age=refresh_max_age, httponly=False),
    )


def clear_auth_cookies(response: Response) -> None:
    for name, httponly in (
        (ACCESS_COOKIE_NAME, True),
        (REFRESH_COOKIE_NAME, True),
        (CSRF_COOKIE_NAME, False),
    ):
        response.set_cookie(name, "", **_cookie_kwargs(max_age=0, httponly=httponly))


def get_access_token(request: Request) -> str | None:
    return request.cookies.get(ACCESS_COOKIE_NAME)


def get_refresh_token(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE_NAME)


def validate_csrf_request(request: Request) -> JSONResponse | None:
    if request.method.upper() in SAFE_METHODS:
        return None
    if request.url.path in CSRF_EXEMPT_PATHS:
        return None
    if not (get_access_token(request) or get_refresh_token(request)):
        return None

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(CSRF_HEADER_NAME)
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF 校验失败，请刷新页面后重试", "code": "CSRF_FAILED"},
        )
    return None
