from fastapi.responses import Response
from starlette.requests import Request

from app.core.auth_cookies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    set_auth_cookies,
    validate_csrf_request,
)
from app.schemas.auth import TokenResponse


def _request(
    *,
    method: str = "POST",
    path: str = "/api/v1/auth/me/",
    cookie: str = "",
    csrf_header: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if csrf_header is not None:
        headers.append((CSRF_HEADER_NAME.lower().encode(), csrf_header.encode()))
    return Request({"type": "http", "method": method, "path": path, "headers": headers})


def test_set_auth_cookies_marks_tokens_http_only_and_csrf_readable():
    response = Response()

    set_auth_cookies(response, TokenResponse(access_token="access.jwt", refresh_token="refresh.jwt"))

    headers = response.headers.getlist("set-cookie")
    assert any(f"{ACCESS_COOKIE_NAME}=access.jwt" in header and "HttpOnly" in header for header in headers)
    assert any(f"{REFRESH_COOKIE_NAME}=refresh.jwt" in header and "HttpOnly" in header for header in headers)
    assert any(f"{CSRF_COOKIE_NAME}=" in header and "HttpOnly" not in header for header in headers)
    assert all("SameSite=strict" in header for header in headers)


def test_clear_auth_cookies_expires_all_auth_cookies():
    response = Response()

    clear_auth_cookies(response)

    headers = response.headers.getlist("set-cookie")
    assert any(f"{ACCESS_COOKIE_NAME}=" in header and "Max-Age=0" in header for header in headers)
    assert any(f"{REFRESH_COOKIE_NAME}=" in header and "Max-Age=0" in header for header in headers)
    assert any(f"{CSRF_COOKIE_NAME}=" in header and "Max-Age=0" in header for header in headers)


def test_csrf_validation_ignores_safe_and_login_requests():
    cookie = f"{ACCESS_COOKIE_NAME}=access.jwt; {CSRF_COOKIE_NAME}=csrf-value"

    assert validate_csrf_request(_request(method="GET", cookie=cookie)) is None
    assert validate_csrf_request(_request(path="/api/v1/auth/login/", cookie=cookie)) is None


def test_csrf_validation_requires_matching_header_for_cookie_auth():
    cookie = f"{ACCESS_COOKIE_NAME}=access.jwt; {CSRF_COOKIE_NAME}=csrf-value"

    missing = validate_csrf_request(_request(cookie=cookie))
    assert missing is not None
    assert missing.status_code == 403

    mismatch = validate_csrf_request(_request(cookie=cookie, csrf_header="wrong"))
    assert mismatch is not None
    assert mismatch.status_code == 403

    assert validate_csrf_request(_request(cookie=cookie, csrf_header="csrf-value")) is None


def test_csrf_validation_allows_bearer_only_clients_without_cookie():
    assert validate_csrf_request(_request()) is None
