"""FastAPI 公共 Depends 依赖（v2 授权体系：角色权限 + 用户组资源组链路）。"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth_cookies import get_access_token
from app.core.database import get_db
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/form/", auto_error=False)
type CurrentUser = dict[str, Any]

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="无法验证凭据",
    headers={"WWW-Authenticate": "Bearer"},
)


async def current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """获取当前登录用户，返回含 permissions + role + user_groups 的完整字典。"""
    return await load_user_context(token or get_access_token(request), db)


async def load_user_context(token: str | None, db: AsyncSession) -> CurrentUser:
    """从 access token 还原完整用户上下文（供 HTTP 依赖与 WebSocket 认证复用）。"""
    if not token:
        raise _401

    try:
        payload = decode_token(token)
    except JWTError:
        raise _401 from None

    user_id = payload.get("sub")
    if not user_id:
        raise _401

    # Token 黑名单检查（fail-close）
    try:
        from redis.asyncio import Redis

        from app.core.config import settings

        r = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        is_blacklisted = await r.exists(f"blacklist:{token}")
        await r.aclose()
        if is_blacklisted:
            raise _401
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用，请稍后重试",
        ) from None

    from app.models.role import Role, UserGroup
    from app.models.user import Users

    # 加载用户 + 角色(含权限码) + 用户组(含资源组)
    result = await db.execute(
        select(Users)
        .options(
            selectinload(Users.user_groups).selectinload(UserGroup.resource_groups),
            selectinload(Users.role).selectinload(Role.permissions),
        )
        .where(Users.id == int(user_id))
    )
    db_user = result.scalar_one_or_none()
    if not db_user or not db_user.is_active:
        raise _401

    # 改密后撤销全部旧会话：token 若在最近一次改密前签发则失效（SAG-012）。
    from app.core.security import is_token_revoked_by_password_change

    if is_token_revoked_by_password_change(payload.get("iat"), db_user.password_changed_at):
        raise _401

    if payload.get("requires_2fa") and not payload.get("2fa_verified"):
        raise HTTPException(status_code=403, detail="请先完成二步验证")

    # ── v2 权限获取：仅角色权限（不再查 user_permission）──
    role_perms: set[str] = set()
    if db_user.role and db_user.role.permissions:
        role_perms = {p.codename for p in db_user.role.permissions}

    # ── v2 资源组获取：仅通过用户组关联（不再查 user_resource_group）──
    group_rg_ids: set[int] = set()
    for ug in db_user.user_groups:
        for rg in ug.resource_groups:
            group_rg_ids.add(rg.id)

    return {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name,
        "is_superuser": db_user.is_superuser,
        "is_active": db_user.is_active,
        "permissions": list(role_perms),
        "role": db_user.role.name if db_user.role else None,
        "role_id": db_user.role_id,
        "manager_id": db_user.manager_id,
        "resource_groups": list(group_rg_ids),
        "user_groups": [ug.id for ug in db_user.user_groups],
        "tenant_id": db_user.tenant_id,
    }


async def current_superuser(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


def require_perm(perm: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """权限校验依赖工厂，用法：Depends(require_perm('sql_review'))"""

    async def _checker(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.get("is_superuser"):
            return user
        if perm not in user.get("permissions", []):
            raise HTTPException(status_code=403, detail=f"缺少权限：{perm}")
        return user

    return _checker


async def authenticate_websocket(websocket: Any, db: AsyncSession) -> CurrentUser | None:
    """WebSocket 握手认证：从 access_token Cookie 或 token 查询参数还原用户，失败返回 None。"""
    from app.core.auth_cookies import ACCESS_COOKIE_NAME

    token = websocket.cookies.get(ACCESS_COOKIE_NAME) or websocket.query_params.get("token")
    try:
        return await load_user_context(token, db)
    except HTTPException:
        return None
