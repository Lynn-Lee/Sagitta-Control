"""
通知服务单元测试。
验证钉钉/飞书/企微三渠道消息发送逻辑（使用 mock HTTP，不依赖真实凭证）。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.system import SystemNotification
from app.services.notify import STATUS_DESC, STATUS_NOTICE, NotifyService
from app.services.notify import NotificationTarget

# ── 辅助 Mock ────────────────────────────────────────────────

def _make_resp(json_data: dict | None = None):
    """构造 httpx 响应 mock。"""
    m = MagicMock()
    m.json.return_value = json_data or {"errcode": 0, "errmsg": "ok"}
    m.raise_for_status = MagicMock()
    return m


def _make_client_mock(json_data: dict | None = None):
    """构造 httpx.AsyncClient context manager mock。"""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_make_resp(json_data))
    return mock_client


# ── 钉钉通知 ──────────────────────────────────────────────────

class TestDingTalkSend:

    @pytest.mark.asyncio
    async def test_send_success(self):
        svc = NotifyService(config={
            "ding_webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            "ding_secret": "",
        })
        with patch("httpx.AsyncClient",
                   return_value=_make_client_mock({"errcode": 0, "errmsg": "ok"})):
            result = await svc._send_dingtalk("测试标题", "测试内容")
        assert result.get("errcode") == 0

    @pytest.mark.asyncio
    async def test_send_with_sign_generates_signature(self):
        """有 secret 时应在 URL 中添加时间戳和签名参数。"""
        svc = NotifyService(config={
            "ding_webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            "ding_secret": "SECxxx",
        })
        captured_url = []
        mock_client = _make_client_mock({"errcode": 0})

        async def capture_post(url, **kwargs):
            captured_url.append(url)
            return _make_resp({"errcode": 0})

        mock_client.post = capture_post
        with patch("httpx.AsyncClient", return_value=mock_client):
            await svc._send_dingtalk("t", "c")

        assert len(captured_url) == 1
        assert "timestamp=" in captured_url[0]
        assert "sign=" in captured_url[0]

    @pytest.mark.asyncio
    async def test_send_raises_on_error_response(self):
        svc = NotifyService(config={
            "ding_webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            "ding_secret": "",
        })
        with patch("httpx.AsyncClient",
                   return_value=_make_client_mock({"errcode": 60020, "errmsg": "token not found"})), \
             pytest.raises(Exception, match="钉钉通知失败"):
            await svc._send_dingtalk("t", "c")


# ── 企业微信通知 ──────────────────────────────────────────────

class TestWecomSend:

    @pytest.mark.asyncio
    async def test_send_success(self):
        svc = NotifyService(config={
            "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
        })
        with patch("httpx.AsyncClient",
                   return_value=_make_client_mock({"errcode": 0, "errmsg": "ok"})):
            result = await svc._send_wecom("测试标题", "测试内容")
        assert result.get("errcode") == 0

    @pytest.mark.asyncio
    async def test_send_raises_on_error(self):
        svc = NotifyService(config={
            "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
        })
        with patch("httpx.AsyncClient",
                   return_value=_make_client_mock({"errcode": 95, "errmsg": "token invalid"})), \
             pytest.raises(Exception, match="企微通知失败"):
            await svc._send_wecom("t", "c")


# ── 飞书通知 ──────────────────────────────────────────────────

class TestFeishuSend:

    @pytest.mark.asyncio
    async def test_send_success(self):
        svc = NotifyService(config={
            "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        })
        with patch("httpx.AsyncClient",
                   return_value=_make_client_mock({"code": 0, "msg": "success"})):
            result = await svc._send_feishu("测试标题", "测试内容")
        assert result.get("code") == 0


# ── notify_workflow 静态方法 ──────────────────────────────────

class TestNotifyWorkflow:

    @pytest.mark.asyncio
    async def test_notify_skips_disabled_channels(self):
        """所有渠道均未启用时，不发送任何通知（不报错）。"""
        mock_db = AsyncMock()
        with patch("app.services.system_config.SystemConfigService.get_value",
                   AsyncMock(return_value="")):
            # 应该正常完成，不抛异常
            await NotifyService.notify_workflow(
                db=mock_db,
                workflow_id=1,
                workflow_name="测试工单",
                status=0,
                operator="admin",
            )

    @pytest.mark.asyncio
    async def test_notify_sends_to_enabled_channels(self):
        """启用的渠道应该被调用。"""
        mock_db = AsyncMock()
        config_map = {
            "ding_webhook":   "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            "ding_secret":    "",
            "ding_enabled":   "true",
            "wecom_webhook":  "",
            "wecom_enabled":  "false",
            "feishu_webhook": "",
            "feishu_enabled": "false",
            "mail_host":      "",
            "mail_user":      "",
            "mail_password":  "",
            "mail_port":      "465",
            "mail_use_ssl":   "false",
            "platform_url":   "http://localhost",
        }

        with (
            patch("app.services.system_config.SystemConfigService.get_value",
                  AsyncMock(side_effect=lambda db, k: config_map.get(k, ""))),
            patch("httpx.AsyncClient",
                  return_value=_make_client_mock({"errcode": 0})),
        ):
            await NotifyService.notify_workflow(
                db=mock_db,
                workflow_id=42,
                workflow_name="上线工单",
                status=6,  # FINISH
                operator="dba_user",
                instance_name="prod-mysql",
                db_name="orders",
            )
        # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_notify_continues_on_channel_failure(self):
        """单个渠道发送失败不应影响整体流程（异常被捕获）。"""
        mock_db = AsyncMock()
        config_map = {
            "ding_webhook":   "https://oapi.dingtalk.com/robot/send?access_token=xxx",
            "ding_secret":    "",
            "ding_enabled":   "true",
            "wecom_webhook":  "https://qyapi.weixin.qq.com/webhook?key=xxx",
            "wecom_enabled":  "true",
            "feishu_webhook": "",
            "feishu_enabled": "false",
            "mail_host":      "",
            "mail_user":      "",
            "mail_password":  "",
            "mail_port":      "465",
            "mail_use_ssl":   "false",
            "platform_url":   "",
        }

        import httpx

        def _fail_client(**kwargs):
            mock = _make_client_mock()
            mock.post = AsyncMock(side_effect=httpx.ConnectError("网络不通"))
            return mock

        with (
            patch("app.services.system_config.SystemConfigService.get_value",
                  AsyncMock(side_effect=lambda db, k: config_map.get(k, ""))),
            patch("httpx.AsyncClient", side_effect=_fail_client),
        ):
            # 不应抛出异常
            await NotifyService.notify_workflow(
                db=mock_db,
                workflow_id=1,
                workflow_name="t",
                status=7,
                operator="admin",
            )


class TestSystemNotification:
    @pytest.mark.asyncio
    async def test_send_event_writes_system_notification_before_external_delivery(self):
        db = MagicMock()
        db.commit = AsyncMock()
        target = NotificationTarget(
            id=7,
            username="approver",
            display_name="审批人",
            email="",
            dingtalk_user_id="",
            feishu_open_id="",
            wecom_userid="",
        )
        payload = {
            "event_type": "approval_pending",
            "subject_type": "workflow",
            "subject_id": 42,
            "app_type": "SQL 工单",
            "title": "上线变更",
            "applicant_name": "申请人",
            "detail_path": "/workflow/42",
        }

        external_send = AsyncMock()
        with (
            patch("app.services.notify.NotifyService._load_config", AsyncMock(return_value={})),
            patch("app.services.notify.NotifyService.resolve_targets", AsyncMock(return_value=[target])),
            patch("app.services.notify.NotifyService._send_to_user", external_send),
        ):
            await NotifyService.send_event(db, payload)

        added = db.add.call_args.args[0]
        assert isinstance(added, SystemNotification)
        assert added.recipient_user_id == 7
        assert added.event_type == "approval_pending"
        assert added.subject_type == "workflow"
        assert added.subject_id == 42
        assert added.detail_path == "/workflow/42"
        assert "待审批提醒" in added.title
        assert external_send.await_count == 1


# ── 状态常量 ──────────────────────────────────────────────────

class TestStatusConstants:
    def test_all_terminal_statuses_have_notice(self):
        """关键工单状态（通过/失败/异常）必须有通知文案。"""
        for status in [0, 2, 6, 7, 8]:
            assert status in STATUS_NOTICE, f"状态 {status} 缺少通知文案"

    def test_all_statuses_have_description(self):
        for status in range(9):
            assert status in STATUS_DESC, f"状态 {status} 缺少描述"
