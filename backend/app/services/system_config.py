"""
系统配置服务。
支持：邮件、钉钉、企微、飞书、LDAP 配置 + 连通性测试。
敏感字段（密码/Token）用 Fernet 加密存储。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.models.system import SystemConfig

logger = logging.getLogger(__name__)

# ── 配置分组定义 ──────────────────────────────────────────────
CONFIG_GROUPS = {
    "basic": "基础设置",
    "mail": "邮件通知",
    "dingtalk": "钉钉",
    "wecom": "企业微信",
    "feishu": "飞书",
    "ldap": "LDAP 认证",
    "cas": "CAS 单点登录",
    "sms": "短信验证码",
    "ai": "AI 功能",
}

# 配置项定义：key → (description, group, is_sensitive, default)
CONFIG_DEFINITIONS: dict[str, tuple[str, str, bool, str]] = {
    # ── 基础 ──────────────────────────────────────────────────
    "platform_name": ("平台名称", "basic", False, "SagittaDB"),
    "platform_url": ("平台访问地址", "basic", False, "http://localhost"),
    "sql_review_limit": ("单次审核SQL最大行数", "basic", False, "1000"),
    "query_default_limit": ("在线查询默认行数限制", "basic", False, "100"),
    "workflow_auto_review": ("启用sqlglot自动审核", "basic", False, "false"),
    # ── 邮件 ──────────────────────────────────────────────────
    "mail_host": ("SMTP服务器地址", "mail", False, ""),
    "mail_port": ("SMTP端口", "mail", False, "465"),
    "mail_use_ssl": ("使用SSL", "mail", False, "true"),
    "mail_user": ("发件人邮箱", "mail", False, ""),
    "mail_password": ("发件人密码/授权码", "mail", True, ""),
    "mail_from": ("发件人显示名", "mail", False, "数据库管理平台"),
    # ── 钉钉 ──────────────────────────────────────────────────
    "ding_webhook": ("通知Webhook地址", "dingtalk", True, ""),
    "ding_secret": ("通知加签密钥", "dingtalk", True, ""),
    "ding_enabled": ("启用钉钉通知", "dingtalk", False, "false"),
    "ding_login_app_id": ("登录 AppKey/ClientId", "dingtalk", False, ""),
    "ding_login_app_secret": ("登录 AppSecret", "dingtalk", True, ""),
    "ding_login_enabled": ("启用钉钉扫码登录", "dingtalk", False, "false"),
    "ding_agent_id": ("工作通知 AgentId", "dingtalk", False, ""),
    # ── 企业微信 ──────────────────────────────────────────────
    "wecom_webhook": ("通知Webhook地址", "wecom", True, ""),
    "wecom_enabled": ("启用企微通知", "wecom", False, "false"),
    "wecom_login_corp_id": ("登录 企业CorpID", "wecom", False, ""),
    "wecom_login_agent_id": ("登录 自建应用AgentId", "wecom", False, ""),
    "wecom_login_app_secret": ("登录 自建应用Secret", "wecom", True, ""),
    "wecom_login_enabled": ("启用企微扫码登录", "wecom", False, "false"),
    # ── 飞书 ──────────────────────────────────────────────────
    "feishu_webhook": ("通知Webhook地址", "feishu", True, ""),
    "feishu_app_id": ("App ID", "feishu", False, ""),
    "feishu_app_secret": ("App Secret", "feishu", True, ""),
    "feishu_enabled": ("启用飞书通知", "feishu", False, "false"),
    "feishu_login_enabled": ("启用飞书扫码登录", "feishu", False, "false"),
    # ── LDAP ──────────────────────────────────────────────────
    "ldap_enabled": ("启用LDAP认证", "ldap", False, "false"),
    "ldap_server_uri": ("LDAP服务器地址", "ldap", False, "ldap://ldap.example.com:389"),
    "ldap_bind_dn": ("Bind DN", "ldap", False, "cn=admin,dc=example,dc=com"),
    "ldap_bind_password": ("Bind 密码", "ldap", True, ""),
    "ldap_user_search_base": ("用户搜索Base DN", "ldap", False, "ou=users,dc=example,dc=com"),
    "ldap_user_filter": ("用户过滤器", "ldap", False, "(uid=%(user)s)"),
    "ldap_attr_username": ("用户名属性", "ldap", False, "uid"),
    "ldap_attr_email": ("邮箱属性", "ldap", False, "mail"),
    "ldap_attr_display": ("显示名属性", "ldap", False, "cn"),
    "ldap_attr_employee_id": ("工号属性", "ldap", False, "employeeId"),
    "ldap_attr_department": ("部门属性", "ldap", False, "department"),
    "ldap_attr_title": ("职位属性", "ldap", False, "title"),
    # ── CAS（Central Authentication Service）────────────────
    "cas_enabled": ("启用 CAS 登录", "cas", False, "false"),
    "cas_server_url": ("CAS 服务器地址", "cas", False, ""),
    "cas_username_attribute": ("用户名属性（留空默认 user）", "cas", False, ""),
    # ── 短信验证码 ──────────────────────────────────────────
    "sms_enabled": ("启用短信验证码登录", "sms", False, "false"),
    "sms_provider": ("短信服务商（aliyun/tencent/custom）", "sms", False, "aliyun"),
    "sms_sign_name": ("短信签名", "sms", False, ""),
    "sms_template_code": ("验证码模板CODE", "sms", False, ""),
    "sms_access_key_id": ("AccessKey ID", "sms", False, ""),
    "sms_access_key_secret": ("AccessKey Secret", "sms", True, ""),
    "sms_endpoint": ("自定义 API 端点（custom 时使用）", "sms", False, ""),
    # ── AI 配置 ───────────────────────────────────────────────
    "ai_enabled": ("启用 AI 功能", "ai", False, "false"),
    "ai_api_key": ("Anthropic API Key", "ai", True, ""),
    "ai_model": ("AI 模型", "ai", False, "claude-sonnet-4-20250514"),
}


class SystemConfigService:
    @staticmethod
    async def _ensure_defaults(db: AsyncSession) -> None:
        """首次调用时初始化所有配置项默认值。"""
        for key, (desc, group, _sensitive, default) in CONFIG_DEFINITIONS.items():
            existing = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            if not existing.scalar_one_or_none():
                db.add(
                    SystemConfig(
                        config_key=key,
                        config_value=default,
                        is_encrypted=False,
                        description=desc,
                        group=group,
                    )
                )
        await db.commit()

    @staticmethod
    async def get_all(db: AsyncSession) -> dict[str, list[dict]]:
        """返回按分组组织的所有配置项（敏感值掩码）。"""
        await SystemConfigService._ensure_defaults(db)
        result = await db.execute(select(SystemConfig))
        configs = result.scalars().all()

        groups: dict[str, list[dict]] = {k: [] for k in CONFIG_GROUPS}
        for cfg in configs:
            group = cfg.group if cfg.group in groups else "basic"
            defn = CONFIG_DEFINITIONS.get(cfg.config_key)
            is_sensitive = defn[2] if defn else cfg.is_encrypted
            groups[group].append(
                {
                    "key": cfg.config_key,
                    "value": "******" if is_sensitive and cfg.config_value else cfg.config_value,
                    "description": cfg.description,
                    "is_sensitive": is_sensitive,
                    "group": cfg.group,
                }
            )

        return {
            "groups": CONFIG_GROUPS,
            "configs": {k: v for k, v in groups.items() if v},
        }

    @staticmethod
    async def get_value(db: AsyncSession, key: str) -> str:
        """获取解密后的配置值（内部使用）。"""
        result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
        cfg = result.scalar_one_or_none()
        if not cfg or not cfg.config_value:
            defn = CONFIG_DEFINITIONS.get(key)
            return defn[3] if defn else ""
        if cfg.is_encrypted:
            return decrypt_field(cfg.config_value)
        return cfg.config_value

    @staticmethod
    async def update_batch(db: AsyncSession, updates: dict[str, str]) -> tuple[int, list[str]]:
        """
        批量更新配置项，敏感字段自动加密。
        返回 (更新数量, 变更摘要列表)，敏感字段只记录 key 不记录值。
        """
        count = 0
        change_summary = []

        for key, value in updates.items():
            if key not in CONFIG_DEFINITIONS:
                continue
            desc, group, is_sensitive, _ = CONFIG_DEFINITIONS[key]

            # 敏感字段且值为空或掩码 → 跳过（不覆盖原值）
            if is_sensitive and value in ("", "******"):
                continue

            result = await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
            cfg = result.scalar_one_or_none()

            if cfg:
                cfg.config_value = encrypt_field(value) if is_sensitive and value else value
                cfg.is_encrypted = is_sensitive and bool(value)
            else:
                db.add(
                    SystemConfig(
                        config_key=key,
                        config_value=encrypt_field(value) if is_sensitive and value else value,
                        is_encrypted=is_sensitive and bool(value),
                        description=desc,
                        group=group,
                    )
                )

            count += 1
            if is_sensitive:
                change_summary.append(f"{desc}（已更新，值加密存储）")
            else:
                display_val = value if len(value) <= 50 else value[:50] + "..."
                change_summary.append(f"{desc} = {display_val}")

        await db.commit()
        logger.info("system_config_updated: %d keys", count)
        return count, change_summary

    # ── 连通性测试 ────────────────────────────────────────────

    @staticmethod
    async def test_mail(db: AsyncSession, to_email: str) -> dict:
        """发送测试邮件。"""
        try:
            import smtplib
            from email.mime.text import MIMEText

            host = await SystemConfigService.get_value(db, "mail_host")
            port = int(await SystemConfigService.get_value(db, "mail_port") or "465")
            use_ssl = (await SystemConfigService.get_value(db, "mail_use_ssl")).lower() == "true"
            user = await SystemConfigService.get_value(db, "mail_user")
            passwd = await SystemConfigService.get_value(db, "mail_password")
            sender = await SystemConfigService.get_value(db, "mail_from") or user

            if not host or not user:
                return {"success": False, "message": "邮件配置不完整，请先填写 SMTP 地址和发件人"}

            msg = MIMEText("这是来自SagittaDB 的测试邮件，收到说明邮件配置正确。", "plain", "utf-8")
            msg["Subject"] = "【SagittaDB】测试邮件"
            msg["From"] = f"{sender} <{user}>"
            msg["To"] = to_email

            if use_ssl:
                smtp = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                smtp = smtplib.SMTP(host, port, timeout=10)
                smtp.starttls()

            smtp.login(user, passwd)
            smtp.sendmail(user, [to_email], msg.as_string())
            smtp.quit()
            return {"success": True, "message": f"测试邮件已发送至 {to_email}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def test_dingtalk(db: AsyncSession) -> dict:
        """发送钉钉测试消息。"""
        try:
            import base64
            import hashlib
            import hmac
            import time
            import urllib.parse

            import httpx

            webhook = await SystemConfigService.get_value(db, "ding_webhook")
            secret = await SystemConfigService.get_value(db, "ding_secret")

            if not webhook:
                return {"success": False, "message": "钉钉 Webhook 未配置"}

            url = webhook
            if secret:
                ts = str(round(time.time() * 1000))
                sign_str = f"{ts}\n{secret}"
                sign = base64.b64encode(
                    hmac.new(secret.encode(), sign_str.encode(), digestmod=hashlib.sha256).digest()
                ).decode()
                url = f"{webhook}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"

            payload = {"msgtype": "text", "text": {"content": "【SagittaDB】钉钉通知测试 ✓"}}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            if data.get("errcode") == 0:
                return {"success": True, "message": "钉钉测试消息发送成功"}
            return {"success": False, "message": f"钉钉返回错误：{data.get('errmsg', '未知')}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def test_wecom(db: AsyncSession) -> dict:
        """发送企业微信测试消息。"""
        try:
            import httpx

            webhook = await SystemConfigService.get_value(db, "wecom_webhook")
            if not webhook:
                return {"success": False, "message": "企业微信 Webhook 未配置"}

            payload = {
                "msgtype": "text",
                "text": {"content": "【SagittaDB】企业微信通知测试 ✓"},
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                data = resp.json()

            if data.get("errcode") == 0:
                return {"success": True, "message": "企业微信测试消息发送成功"}
            return {"success": False, "message": f"企微返回错误：{data.get('errmsg', '未知')}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def test_feishu(db: AsyncSession) -> dict:
        """发送飞书测试消息。"""
        try:
            import httpx

            webhook = await SystemConfigService.get_value(db, "feishu_webhook")
            if not webhook:
                return {"success": False, "message": "飞书 Webhook 未配置"}

            payload = {
                "msg_type": "text",
                "content": {"text": "【SagittaDB】飞书通知测试 ✓"},
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                data = resp.json()

            if data.get("code") == 0 or data.get("StatusCode") == 0:
                return {"success": True, "message": "飞书测试消息发送成功"}
            return {"success": False, "message": f"飞书返回：{data}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def test_ldap(db: AsyncSession, test_username: str, test_password: str) -> dict:
        """测试 LDAP 连接。"""
        try:
            import ldap3

            server_uri = await SystemConfigService.get_value(db, "ldap_server_uri")
            bind_dn = await SystemConfigService.get_value(db, "ldap_bind_dn")
            bind_pwd = await SystemConfigService.get_value(db, "ldap_bind_password")

            if not server_uri:
                return {"success": False, "message": "LDAP 服务器地址未配置"}

            server = ldap3.Server(server_uri, connect_timeout=10)
            conn = ldap3.Connection(server, bind_dn, bind_pwd, auto_bind=True)
            conn.unbind()
            return {"success": True, "message": "LDAP 服务器连接成功"}
        except ImportError:
            return {
                "success": False,
                "message": "ldap3 库未安装，请在 Dockerfile 中添加 ldap3 依赖",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}
