"""系统管理子路由。"""

from typing import Any
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.services.audit_log import AuditLogService
from app.services.license import LicenseService
from app.services.system_config import SystemConfigService

from .schemas import ConfigUpdateRequest, LdapTestRequest, MailTestRequest, NotifyUserTestRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 系统配置
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
# 站内通知
# ═══════════════════════════════════════════════════════════


@router.get("/notifications/", summary="我的站内通知")
async def list_my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    total, items = await NotifyService.list_system_notifications(
        db,
        user_id=user["id"],
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/notifications/unread-count/", summary="我的未读通知数")
async def get_my_notification_unread_count(
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    return {"count": await NotifyService.unread_count(db, user["id"])}


@router.get("/notifications/delivery-log/", summary="通知投递日志")
async def list_notification_delivery_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    event_type: str | None = None,
    subject_type: str | None = None,
    subject_id: int | None = Query(None, ge=0),
    channel: str | None = Query(None, pattern="^(feishu|wecom|dingtalk|mail|none)$"),
    status: str | None = Query(None, pattern="^(sent|failed|skipped|pending)$"),
    recipient_user_id: int | None = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    total, items = await NotifyService.list_delivery_logs(
        db,
        page=page,
        page_size=page_size,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        channel=channel,
        status=status,
        recipient_user_id=recipient_user_id,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/notifications/missing-external-ids/", summary="外部通知账号缺失检查")
async def list_notification_missing_external_ids(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    approval_only: bool = True,
    missing_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    total, items = await NotifyService.list_missing_external_ids(
        db,
        approval_only=approval_only,
        missing_only=missing_only,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/notifications/read-all/", summary="全部通知标记已读")
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    count = await NotifyService.mark_all_read(db, user["id"])
    return {"status": 0, "msg": "已全部标记为已读", "data": {"count": count}}


@router.post("/notifications/{notification_id}/read/", summary="通知标记已读")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(current_user),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    ok = await NotifyService.mark_read(db, user["id"], notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="通知不存在")
    return {"status": 0, "msg": "已标记为已读"}


@router.get("/config/", summary="获取系统配置（按分组）")
async def get_system_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.get_all(db)


@router.get("/branding/", summary="获取公开品牌配置")
async def get_public_branding(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await SystemConfigService.get_branding(db)


@router.get("/auth-methods/", summary="获取公开登录方式配置")
async def get_public_auth_methods(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await SystemConfigService.get_public_auth_methods(db)


@router.post("/config/", summary="批量更新系统配置")
async def update_system_config(
    data: ConfigUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    try:
        count, change_summary = await SystemConfigService.update_batch(db, data.updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 审计日志记录具体变更项（敏感字段只记key，不记值）
    detail = (
        f"更新 {count} 个配置项：" + "；".join(change_summary)
        if change_summary
        else f"更新 {count} 个配置项"
    )
    await AuditLogService.write(
        db,
        user,
        action="update_config",
        module="system",
        detail=detail,
        request=request,
    )
    return {"status": 0, "msg": f"已保存 {count} 个配置项", "count": count}


@router.post("/config/test/mail/", summary="测试邮件配置")
async def test_mail_config(
    data: MailTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    result = await SystemConfigService.test_mail(db, data.to_email)
    return result


@router.post("/config/test/dingtalk/", summary="测试钉钉配置")
async def test_dingtalk_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_dingtalk(db)


@router.post("/config/test/wecom/", summary="测试企业微信配置")
async def test_wecom_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_wecom(db)


@router.post("/config/test/feishu/", summary="测试飞书配置")
async def test_feishu_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_feishu(db)


@router.post("/config/test/ai/", summary="测试 AI 配置")
async def test_ai_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    license_check = await LicenseService.check_access(db, "/api/v1/ai/text2sql/", "POST")
    if not license_check.allowed:
        return {
            "success": False,
            "message": license_check.reason or "当前 License 未授权 AI 功能",
        }
    return await SystemConfigService.test_ai(db)


@router.post("/config/test/notify-user/", summary="测试应用消息精准通知")
async def test_notify_user_config(
    data: NotifyUserTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    from app.services.notify import NotifyService

    await NotifyService.send_event(
        db,
        {
            "event_type": "approval_pending",
            "subject_type": "system_config",
            "subject_id": 0,
            "app_type": "系统配置",
            "title": "主动通知测试",
            "applicant_id": data.user_id,
            "applicant_name": "系统配置",
            "user_ids": [data.user_id],
            "remark": "如果你收到这条消息，说明精准通知配置可用。",
            "detail_path": "/system/config",
        },
    )
    return {"success": True, "message": "测试通知已发送，请查看投递日志确认各渠道结果"}


@router.post("/config/test/ldap/", summary="测试 LDAP 配置")
async def test_ldap_config(
    data: LdapTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_ldap(db, data.test_username, data.test_password)


@router.post("/config/test/cas/", summary="测试 CAS 配置")
async def test_cas_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_cas(db)


@router.post("/config/test/oidc/", summary="测试 OIDC 配置")
async def test_oidc_config(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any]=Depends(require_perm("system_config_manage")),
) -> dict[str, Any]:
    return await SystemConfigService.test_oidc(db)
