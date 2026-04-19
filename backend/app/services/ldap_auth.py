"""
LDAP 认证服务（Pack F-P0）。

读取系统配置中的 LDAP 参数，通过 ldap3 完成：
  1. Bind DN 绑定验证服务账号可用性
  2. 在 search_base 下按 user_filter 搜索目标用户 DN
  3. 以用户 DN + 密码 re-bind，验证密码正确
  4. 自动 provision 用户（auth_type='ldap'），已存在则更新属性
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import Users
from app.services.system_config import SystemConfigService

logger = logging.getLogger(__name__)


class LdapAuthService:
    @staticmethod
    async def _get_ldap_config(db: AsyncSession) -> dict[str, str]:
        keys = [
            "ldap_enabled",
            "ldap_server_uri",
            "ldap_bind_dn",
            "ldap_bind_password",
            "ldap_user_search_base",
            "ldap_user_filter",
            "ldap_attr_username",
            "ldap_attr_email",
            "ldap_attr_display",
            "ldap_attr_employee_id",
            "ldap_attr_department",
            "ldap_attr_title",
        ]
        return {k: await SystemConfigService.get_value(db, k) for k in keys}

    @staticmethod
    async def authenticate(
        db: AsyncSession,
        username: str,
        password: str,
    ) -> Users:
        """
        验证 LDAP 凭据并返回对应的本地用户（自动创建/更新）。

        Raises:
            ValueError: LDAP 未启用、配置不完整、用户不存在或密码错误。
        """
        try:
            import ldap3
            import ldap3.core.exceptions as ldap_exc
        except ImportError as e:
            raise ValueError("ldap3 库未安装，请联系管理员") from e

        cfg = await LdapAuthService._get_ldap_config(db)

        if cfg.get("ldap_enabled", "false").lower() != "true":
            raise ValueError("LDAP 认证未启用")

        server_uri = cfg.get("ldap_server_uri", "")
        bind_dn = cfg.get("ldap_bind_dn", "")
        bind_pwd = cfg.get("ldap_bind_password", "")
        search_base = cfg.get("ldap_user_search_base", "")
        user_filter = cfg.get("ldap_user_filter", "(uid=%(user)s)")
        attr_username = cfg.get("ldap_attr_username", "uid")
        attr_email = cfg.get("ldap_attr_email", "mail")
        attr_display = cfg.get("ldap_attr_display", "cn")
        attr_employee_id = cfg.get("ldap_attr_employee_id", "employeeId")
        attr_department = cfg.get("ldap_attr_department", "department")
        attr_title = cfg.get("ldap_attr_title", "title")

        if not server_uri or not search_base:
            raise ValueError("LDAP 配置不完整，请在系统配置中填写服务器地址和搜索Base DN")

        # 将 %(user)s 替换为实际用户名（ldap3 不支持这种格式，手动替换）
        search_filter = user_filter % {"user": ldap3.utils.conv.escape_filter_chars(username)}

        server = ldap3.Server(server_uri, connect_timeout=10, get_info=ldap3.NONE)

        # Step 1: 用 service account 搜索用户 DN
        try:
            svc_conn = ldap3.Connection(
                server,
                bind_dn,
                bind_pwd,
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
                raise_exceptions=True,
            )
        except ldap_exc.LDAPException as e:
            raise ValueError(f"LDAP 服务账号绑定失败: {e}") from e

        try:
            svc_conn.search(
                search_base=search_base,
                search_filter=search_filter,
                attributes=[
                    attr_username,
                    attr_email,
                    attr_display,
                    attr_employee_id,
                    attr_department,
                    attr_title,
                ],
            )
        except ldap_exc.LDAPException as e:
            raise ValueError(f"LDAP 搜索失败: {e}") from e

        if not svc_conn.entries:
            raise ValueError("用户不存在或不在允许的搜索范围内")

        entry = svc_conn.entries[0]
        user_dn = entry.entry_dn

        # 提取属性（ldap3 entries 均为列表，取第一个元素）
        def _attr(name: str, default: str = "") -> str:
            try:
                val = getattr(entry, name, None)
                if val is None:
                    return default
                values = val.values
                return str(values[0]) if values else default
            except Exception:
                return default

        ldap_username = _attr(attr_username, username)
        ldap_email = _attr(attr_email, "")
        ldap_display = _attr(attr_display, ldap_username)
        ldap_employee_id = _attr(attr_employee_id, "")
        ldap_department = _attr(attr_department, "")
        ldap_title = _attr(attr_title, "")

        svc_conn.unbind()

        # Step 2: 以用户 DN + 密码验证
        try:
            user_conn = ldap3.Connection(
                server,
                user_dn,
                password,
                auto_bind=ldap3.AUTO_BIND_NO_TLS,
                raise_exceptions=True,
            )
            user_conn.unbind()
        except ldap_exc.LDAPInvalidCredentialsResult as e:
            raise ValueError("LDAP 密码错误") from e
        except ldap_exc.LDAPException as e:
            raise ValueError(f"LDAP 认证失败: {e}") from e

        # Step 3: 自动 provision 本地用户
        user = await LdapAuthService._provision_user(
            db,
            ldap_username,
            ldap_email,
            ldap_display,
            user_dn,
            employee_id=ldap_employee_id,
            department=ldap_department,
            title=ldap_title,
        )
        return user

    @staticmethod
    async def _provision_user(
        db: AsyncSession,
        username: str,
        email: str,
        display_name: str,
        external_id: str,
        employee_id: str = "",
        department: str = "",
        title: str = "",
    ) -> Users:
        """查找或创建 LDAP 用户（auth_type='ldap'），并更新可变属性。"""
        # 先按 external_id 查（用户可能改了用户名）
        result = await db.execute(
            select(Users).where(
                Users.auth_type == "ldap",
                Users.external_id == external_id,
            )
        )
        user = result.scalar_one_or_none()

        if user is None:
            # 再按用户名查（兼容首次迁移）
            result = await db.execute(select(Users).where(Users.username == username))
            user = result.scalar_one_or_none()

        if user is None:
            user = Users(
                username=username,
                password=hash_password("__ldap_no_local_password__"),
                display_name=display_name or username,
                email=email or "",
                auth_type="ldap",
                external_id=external_id,
                is_active=True,
                employee_id=employee_id,
                department=department,
                title=title,
                password_changed_at=datetime.now(UTC),
            )
            db.add(user)
            logger.info("ldap_user_provisioned: %s", username)
        else:
            # 更新可变属性
            user.auth_type = "ldap"
            user.external_id = external_id
            if display_name:
                user.display_name = display_name
            if email:
                user.email = email
            if employee_id:
                user.employee_id = employee_id
            if department:
                user.department = department
            if title:
                user.title = title

        await db.commit()
        await db.refresh(user)
        return user
