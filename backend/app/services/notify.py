"""
主动通知服务。

用于 SQL 工单、查询权限申请、数据归档申请的全生命周期提醒。精准通知优先走
飞书/企微/钉钉应用消息；缺少外部账号时降级到邮件；所有投递结果写入日志。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import smtplib
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import (
    Role,
    group_resource_group,
    role_permission,
    user_group_member,
)
from app.models.system import NotificationDeliveryLog, SystemNotification
from app.models.user import Permission, Users

logger = logging.getLogger(__name__)

EVENT_TITLES = {
    "approval_pending": "待审批提醒",
    "approval_passed": "审批通过",
    "approval_rejected": "审批驳回",
    "application_canceled": "申请取消",
    "ready_to_execute": "待执行提醒",
    "execution_started": "执行开始",
    "execution_succeeded": "执行成功",
    "execution_failed": "执行失败",
    "alert_firing": "告警触发",
    "alert_resolved": "告警恢复",
}

EVENT_TEMPLATE = {
    "approval_pending": "blue",
    "approval_passed": "green",
    "approval_rejected": "red",
    "application_canceled": "grey",
    "ready_to_execute": "orange",
    "execution_started": "blue",
    "execution_succeeded": "green",
    "execution_failed": "red",
    "alert_firing": "red",
    "alert_resolved": "green",
}

# 旧测试和旧调用仍依赖这两个常量。
STATUS_NOTICE = {
    0: ("工单待审核", "#1558A8"),
    1: ("工单已驳回", "#f5222d"),
    2: ("工单审核通过", "#52c41a"),
    6: ("工单执行成功", "#52c41a"),
    7: ("工单执行异常", "#fa8c16"),
    8: ("工单已取消", "#AEAEB2"),
}

STATUS_DESC = {
    0: "待审核", 1: "审批驳回", 2: "审核通过",
    3: "定时执行", 4: "队列中", 5: "执行中",
    6: "执行成功", 7: "执行异常", 8: "已取消",
}


@dataclass(frozen=True)
class NotificationTarget:
    id: int
    username: str
    display_name: str
    email: str
    dingtalk_user_id: str
    feishu_open_id: str
    wecom_userid: str


class NotifyService:
    """统一通知入口。"""

    def __init__(self, config: dict[str, str]):
        self.config = config

    # ── 事件入队 ─────────────────────────────────────────────

    @staticmethod
    def enqueue_event(payload: dict[str, Any]) -> None:
        """投递通知任务到 Celery notify 队列。"""
        try:
            from app.tasks.notify import send_notification_event_task

            send_notification_event_task.delay(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification_enqueue_failed: event=%s error=%s", payload.get("event_type"), exc)

    @staticmethod
    async def send_event(db: AsyncSession, payload: dict[str, Any]) -> None:
        config = await NotifyService._load_config(db)
        svc = NotifyService(config)
        targets = await NotifyService.resolve_targets(
            db,
            node=payload.get("node"),
            user_ids=payload.get("user_ids"),
            permission=payload.get("permission"),
            permissions=payload.get("permissions"),
            applicant_id=payload.get("applicant_id"),
            exclude_user_ids=set(payload.get("exclude_user_ids") or []),
        )
        if not targets:
            await NotifyService._write_log(
                db,
                payload,
                channel="none",
                recipient_user_id=None,
                recipient="",
                status="skipped",
                error="没有解析到可通知用户",
            )
            await db.commit()
            return

        subject, content = NotifyService._render(payload, config)
        for target in targets:
            await NotifyService._write_system_notification(db, payload, subject, content, target)
            await svc._send_to_user(db, payload, subject, content, target)
        await db.commit()

    # ── 站内通知 ─────────────────────────────────────────────

    @staticmethod
    async def list_system_notifications(
        db: AsyncSession,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[int, list[dict[str, Any]]]:
        stmt = select(SystemNotification).where(SystemNotification.recipient_user_id == user_id)
        if unread_only:
            stmt = stmt.where(SystemNotification.is_read.is_(False))
        total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
        total = int(total_result.scalar() or 0)
        result = await db.execute(
            stmt.order_by(SystemNotification.created_at.desc(), SystemNotification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, [NotifyService._serialize_system_notification(item) for item in result.scalars().all()]

    @staticmethod
    async def unread_count(db: AsyncSession, user_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(SystemNotification)
            .where(
                SystemNotification.recipient_user_id == user_id,
                SystemNotification.is_read.is_(False),
            )
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def mark_read(db: AsyncSession, user_id: int, notification_id: int) -> bool:
        item = await db.get(SystemNotification, notification_id)
        if not item or item.recipient_user_id != user_id:
            return False
        if not item.is_read:
            item.is_read = True
            item.read_at = datetime.now(UTC)
            await db.commit()
        return True

    @staticmethod
    async def mark_all_read(db: AsyncSession, user_id: int) -> int:
        result = await db.execute(
            select(SystemNotification).where(
                SystemNotification.recipient_user_id == user_id,
                SystemNotification.is_read.is_(False),
            )
        )
        items = result.scalars().all()
        now = datetime.now(UTC)
        for item in items:
            item.is_read = True
            item.read_at = now
        await db.commit()
        return len(items)

    @staticmethod
    async def _write_system_notification(
        db: AsyncSession,
        payload: dict[str, Any],
        title: str,
        content: str,
        target: NotificationTarget,
    ) -> None:
        db.add(
            SystemNotification(
                recipient_user_id=target.id,
                event_type=payload.get("event_type", ""),
                subject_type=payload.get("subject_type", ""),
                subject_id=int(payload.get("subject_id") or 0),
                title=title[:200],
                content=content,
                detail_path=str(payload.get("detail_path") or "")[:500],
            )
        )

    @staticmethod
    def _serialize_system_notification(item: SystemNotification) -> dict[str, Any]:
        return {
            "id": item.id,
            "event_type": item.event_type,
            "subject_type": item.subject_type,
            "subject_id": item.subject_id,
            "title": item.title,
            "content": item.content,
            "detail_path": item.detail_path,
            "is_read": item.is_read,
            "created_at": item.created_at.isoformat() if item.created_at else "",
            "read_at": item.read_at.isoformat() if item.read_at else None,
        }

    # ── 收件人解析 ───────────────────────────────────────────

    @staticmethod
    async def resolve_targets(
        db: AsyncSession,
        *,
        node: dict | None = None,
        user_ids: list[int] | None = None,
        permission: str | None = None,
        permissions: list[str] | None = None,
        applicant_id: int | None = None,
        exclude_user_ids: set[int] | None = None,
    ) -> list[NotificationTarget]:
        ids: set[int] = set(user_ids or [])
        if permission:
            ids.update(await NotifyService._user_ids_by_permissions(db, [permission]))
        if permissions:
            ids.update(await NotifyService._user_ids_by_permissions(db, permissions))
        if node:
            ids.update(await NotifyService._user_ids_by_node(db, node, applicant_id))
        if exclude_user_ids:
            ids.difference_update(exclude_user_ids)
        if not ids:
            return []
        result = await db.execute(
            select(Users)
            .where(Users.id.in_(ids), Users.is_active.is_(True))
            .order_by(Users.id)
        )
        return [NotifyService._target_from_user(user) for user in result.scalars().all()]

    @staticmethod
    async def _user_ids_by_node(db: AsyncSession, node: dict, applicant_id: int | None) -> set[int]:
        approver_type = node.get("approver_type", "any_reviewer")
        if approver_type == "users":
            return {int(uid) for uid in (node.get("approver_ids") or [])}
        if approver_type == "manager":
            applicant = await db.get(Users, node.get("applicant_id") or applicant_id)
            return {applicant.manager_id} if applicant and applicant.manager_id else set()
        if approver_type == "any_reviewer":
            permission = node.get("required_permission", "sql_review")
            return await NotifyService._user_ids_by_permissions(db, [permission])
        if approver_type == "user_group":
            group_id = node.get("approver_group_id")
            if not group_id:
                return set()
            result = await db.execute(
                select(user_group_member.c.user_id).where(user_group_member.c.group_id == group_id)
            )
            return set(result.scalars().all())
        if approver_type == "role":
            role_id = node.get("approver_role_id")
            if not role_id:
                return set()
            result = await db.execute(select(Users.id).where(Users.role_id == role_id))
            return set(result.scalars().all())
        if approver_type == "group":
            group_ids = [int(gid) for gid in (node.get("approver_ids") or [])]
            if not group_ids:
                return set()
            result = await db.execute(
                select(user_group_member.c.user_id)
                .join(group_resource_group, user_group_member.c.group_id == group_resource_group.c.group_id)
                .where(group_resource_group.c.resource_group_id.in_(group_ids))
            )
            return set(result.scalars().all())
        return set()

    @staticmethod
    async def _user_ids_by_permissions(db: AsyncSession, permissions: list[str]) -> set[int]:
        result = await db.execute(
            select(Users.id)
            .outerjoin(Role, Users.role_id == Role.id)
            .outerjoin(role_permission, Role.id == role_permission.c.role_id)
            .outerjoin(Permission, Permission.id == role_permission.c.permission_id)
            .where(
                Users.is_active.is_(True),
                (Users.is_superuser.is_(True)) | (Permission.codename.in_(permissions)),
            )
            .distinct()
        )
        return set(result.scalars().all())

    @staticmethod
    def _target_from_user(user: Users) -> NotificationTarget:
        return NotificationTarget(
            id=user.id,
            username=user.username,
            display_name=user.display_name or user.username,
            email=user.email or "",
            dingtalk_user_id=getattr(user, "dingtalk_user_id", "") or "",
            feishu_open_id=getattr(user, "feishu_open_id", "") or "",
            wecom_userid=getattr(user, "wecom_userid", "") or "",
        )

    # ── 发送 ─────────────────────────────────────────────────

    async def _send_to_user(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
        subject: str,
        content: str,
        target: NotificationTarget,
    ) -> None:
        app_attempted = False
        app_succeeded = False
        if self.config.get("feishu_enabled") == "true" and target.feishu_open_id:
            app_attempted = True
            app_succeeded = await self._deliver(db, payload, "feishu", target, target.feishu_open_id, self._send_feishu_user(subject, content, target.feishu_open_id)) or app_succeeded
        if self.config.get("wecom_enabled") == "true" and target.wecom_userid:
            app_attempted = True
            app_succeeded = await self._deliver(db, payload, "wecom", target, target.wecom_userid, self._send_wecom_user(subject, content, target.wecom_userid)) or app_succeeded
        if self.config.get("ding_enabled") == "true" and target.dingtalk_user_id:
            app_attempted = True
            app_succeeded = await self._deliver(db, payload, "dingtalk", target, target.dingtalk_user_id, self._send_dingtalk_user(subject, content, target.dingtalk_user_id)) or app_succeeded
        if target.email and (not app_attempted or not app_succeeded):
            await self._deliver(db, payload, "mail", target, target.email, self._send_mail(subject, content, [target.email]))
            return
        if not app_attempted:
            await NotifyService._write_log(
                db, payload, "none", target.id, target.username, "skipped", "用户未配置外部通知账号或邮箱"
            )

    async def _deliver(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
        channel: str,
        target: NotificationTarget,
        recipient: str,
        coro,
    ) -> bool:
        try:
            await coro
            await NotifyService._write_log(db, payload, channel, target.id, recipient, "sent", "")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("notify_delivery_failed: channel=%s user=%s error=%s", channel, target.username, exc)
            await NotifyService._write_log(db, payload, channel, target.id, recipient, "failed", str(exc))
            return False

    # ── 应用消息实现 ─────────────────────────────────────────

    async def _send_feishu_user(self, title: str, content: str, open_id: str) -> dict:
        app_id = self.config.get("feishu_app_id", "")
        app_secret = self.config.get("feishu_app_secret", "")
        if not app_id or not app_secret:
            raise RuntimeError("飞书应用消息配置不完整")
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
            )
            token_data = token_resp.json()
            token = token_data.get("tenant_access_token")
            if not token:
                raise RuntimeError(f"飞书 token 获取失败：{token_data}")
            resp = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": open_id,
                    "msg_type": "interactive",
                    "content": self._feishu_card_content(title, content),
                },
            )
            data = resp.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(f"飞书应用消息失败：{data}")
        return data

    async def _send_wecom_user(self, title: str, content: str, userid: str) -> dict:
        corp_id = self.config.get("wecom_login_corp_id", "")
        secret = self.config.get("wecom_login_app_secret", "")
        agent_id = self.config.get("wecom_login_agent_id", "")
        if not corp_id or not secret or not agent_id:
            raise RuntimeError("企微应用消息配置不完整")
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": corp_id, "corpsecret": secret},
            )
            token_data = token_resp.json()
            token = token_data.get("access_token")
            if not token:
                raise RuntimeError(f"企微 token 获取失败：{token_data}")
            resp = await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": token},
                json={
                    "touser": userid,
                    "msgtype": "textcard",
                    "agentid": int(agent_id),
                    "textcard": {
                        "title": title,
                        "description": content.replace("\n", "<br>"),
                        "url": self._first_url(content) or self.config.get("platform_url", "http://localhost"),
                    },
                    "safe": 0,
                },
            )
            data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"企微应用消息失败：{data}")
        return data

    async def _send_dingtalk_user(self, title: str, content: str, userid: str) -> dict:
        app_key = self.config.get("ding_login_app_id", "")
        app_secret = self.config.get("ding_login_app_secret", "")
        agent_id = self.config.get("ding_agent_id") or self.config.get("ding_login_agent_id", "")
        if not app_key or not app_secret or not agent_id:
            raise RuntimeError("钉钉工作通知配置不完整")
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.get(
                "https://oapi.dingtalk.com/gettoken",
                params={"appkey": app_key, "appsecret": app_secret},
            )
            token_data = token_resp.json()
            token = token_data.get("access_token")
            if not token:
                raise RuntimeError(f"钉钉 token 获取失败：{token_data}")
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2",
                params={"access_token": token},
                json={
                    "agent_id": int(agent_id),
                    "userid_list": userid,
                    "msg": {"msgtype": "markdown", "markdown": {"title": title, "text": content}},
                },
            )
            data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"钉钉工作通知失败：{data}")
        return data

    # ── 旧 Webhook 通知与邮件 ───────────────────────────────

    @staticmethod
    async def notify_workflow(
        db,
        workflow_id: int,
        workflow_name: str,
        status: int,
        operator: str,
        instance_name: str = "",
        db_name: str = "",
        remark: str = "",
    ) -> None:
        """兼容旧调用：仍发送到已启用的群机器人。"""
        config = await NotifyService._load_config(db)
        svc = NotifyService(config)
        title, _color = STATUS_NOTICE.get(status, ("工单状态变更", "#1558A8"))
        content = "\n".join(
            [
                f"**{title}**",
                f"工单名称：{workflow_name}",
                f"工单ID：#{workflow_id}",
                f"状态：{STATUS_DESC.get(status, '未知')}",
                f"操作人：{operator}",
                *( [f"目标实例：{instance_name}"] if instance_name else [] ),
                *( [f"数据库：{db_name}"] if db_name else [] ),
                *( [f"备注：{remark}"] if remark else [] ),
                f"时间：{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                f"[查看详情]({config.get('platform_url', 'http://localhost')}/workflow/{workflow_id})",
            ]
        )
        tasks = []
        if config.get("ding_enabled") == "true" and config.get("ding_webhook"):
            tasks.append(svc._send_dingtalk(title, content))
        if config.get("wecom_enabled") == "true" and config.get("wecom_webhook"):
            tasks.append(svc._send_wecom(title, content))
        if config.get("feishu_enabled") == "true" and config.get("feishu_webhook"):
            tasks.append(svc._send_feishu(title, content))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_dingtalk(self, title: str, content: str) -> dict:
        import httpx

        webhook = self.config.get("ding_webhook", "")
        secret = self.config.get("ding_secret", "")
        url = webhook
        if secret:
            ts = str(round(time.time() * 1000))
            sign_str = f"{ts}\n{secret}"
            sign = base64.b64encode(
                hmac.new(secret.encode(), sign_str.encode(), digestmod=hashlib.sha256).digest()
            ).decode()
            url = f"{webhook}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"msgtype": "markdown", "markdown": {"title": title, "text": content}, "at": {"isAtAll": False}})
            data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"钉钉通知失败：{data.get('errmsg', '未知错误')}")
        return data

    async def _send_wecom(self, title: str, content: str) -> dict:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.config.get("wecom_webhook", ""), json={"msgtype": "markdown", "markdown": {"content": content}})
            data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"企微通知失败：{data.get('errmsg', '未知错误')}")
        return data

    async def _send_feishu(self, title: str, content: str) -> dict:
        import httpx

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.config.get("feishu_webhook", ""), json=payload)
            data = resp.json()
        code = data.get("code") or data.get("StatusCode")
        if code and code != 0:
            raise Exception(f"飞书通知失败：{data}")
        return data

    async def _send_mail(self, subject: str, content: str, to_emails: list[str]) -> None:
        host = self.config.get("mail_host", "")
        port = int(self.config.get("mail_port", "465") or "465")
        use_ssl = self.config.get("mail_use_ssl", "true").lower() == "true"
        user = self.config.get("mail_user", "")
        password = self.config.get("mail_password", "")
        sender = self.config.get("mail_from") or user
        if not host or not user or not to_emails:
            raise RuntimeError("邮件配置不完整或收件人为空")

        def send_sync() -> None:
            msg = MIMEText(NotifyService._markdown_to_html(content), "html", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{sender} <{user}>" if sender and sender != user else user
            msg["To"] = ", ".join(to_emails)
            if use_ssl:
                smtp = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                smtp = smtplib.SMTP(host, port, timeout=10)
                smtp.starttls()
            try:
                smtp.login(user, password)
                smtp.sendmail(user, to_emails, msg.as_string())
            finally:
                smtp.quit()

        await asyncio.to_thread(send_sync)

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    async def _load_config(db: AsyncSession) -> dict[str, str]:
        from app.services.system_config import SystemConfigService

        keys = [
            "ding_webhook", "ding_secret", "ding_enabled", "ding_login_app_id", "ding_login_app_secret", "ding_agent_id",
            "wecom_webhook", "wecom_enabled", "wecom_login_corp_id", "wecom_login_agent_id", "wecom_login_app_secret",
            "feishu_webhook", "feishu_enabled", "feishu_app_id", "feishu_app_secret",
            "mail_host", "mail_user", "mail_password", "mail_port", "mail_use_ssl", "mail_from",
            "platform_url",
        ]
        return {key: await SystemConfigService.get_value(db, key) for key in keys}

    @staticmethod
    def _render(payload: dict[str, Any], config: dict[str, str]) -> tuple[str, str]:
        event_type = payload.get("event_type", "")
        app_type = payload.get("app_type", "申请")
        title = f"【{app_type}】{EVENT_TITLES.get(event_type, '状态提醒')}"
        platform_url = (config.get("platform_url") or "http://localhost").rstrip("/")
        detail_path = payload.get("detail_path") or ""
        detail_url = f"{platform_url}{detail_path}" if detail_path.startswith("/") else platform_url
        lines = [
            f"**{title}**",
            f"标题：{payload.get('title') or '-'}",
            f"编号：#{payload.get('subject_id') or '-'}",
            f"申请人：{payload.get('applicant_name') or '-'}",
        ]
        if payload.get("node_name"):
            lines.append(f"当前节点：{payload['node_name']}")
        if payload.get("instance_name"):
            lines.append(f"实例：{payload['instance_name']}")
        if payload.get("db_name"):
            lines.append(f"数据库：{payload['db_name']}")
        if payload.get("table_name"):
            lines.append(f"表：{payload['table_name']}")
        if payload.get("risk_level"):
            lines.append(f"风险等级：{payload['risk_level']}")
        if payload.get("remark"):
            lines.append(f"备注：{payload['remark']}")
        lines.append(f"时间：{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"[查看详情]({detail_url})")
        return title, "\n".join(lines)

    @staticmethod
    async def _write_log(
        db: AsyncSession,
        payload: dict[str, Any],
        channel: str,
        recipient_user_id: int | None,
        recipient: str,
        status: str,
        error: str,
    ) -> None:
        db.add(
            NotificationDeliveryLog(
                event_type=payload.get("event_type", ""),
                subject_type=payload.get("subject_type", ""),
                subject_id=int(payload.get("subject_id") or 0),
                channel=channel,
                recipient_user_id=recipient_user_id,
                recipient=recipient,
                status=status,
                error=error[:2000],
            )
        )

    @staticmethod
    def _feishu_card_content(title: str, content: str) -> str:
        import json

        return json.dumps(
            {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": EVENT_TEMPLATE.get("approval_pending", "blue"),
                },
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _markdown_to_html(content: str) -> str:
        html = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = html.replace("\n", "<br>")
        html = html.replace("**", "<b>", 1).replace("**", "</b>", 1)
        return html

    @staticmethod
    def _first_url(content: str) -> str:
        marker = "]("
        if marker not in content:
            return ""
        tail = content.split(marker, 1)[1]
        return tail.split(")", 1)[0]
