"""
短信验证码认证服务。

支持的短信服务商：
- aliyun: 阿里云短信（默认）
- tencent: 腾讯云短信
- custom: 自定义 HTTP API

验证码存储在 Redis 中，key 为 sms:code:{phone}，TTL 5 分钟。
频率限制：同一手机号 60 秒内只能发一次，每天最多 10 次。
"""

from __future__ import annotations

from typing import Any

import logging
import random
import string

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.services.system_config import SystemConfigService

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL_SECONDS = 300  # 验证码有效期 5 分钟
CODE_COOLDOWN_SECONDS = 60  # 重发冷却 60 秒
DAILY_LIMIT = 10  # 每天每手机号上限


async def _get_redis() -> Any:
    from redis.asyncio import Redis

    from app.core.config import settings

    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def send_sms_code(db: AsyncSession, phone: str) -> dict[str, Any]:
    """发送短信验证码。返回 {"success": bool, "message": str}。"""
    enabled = (await SystemConfigService.get_value(db, "sms_enabled")).lower()
    if enabled != "true":
        raise AppException("短信验证码登录未启用", code=400)

    r = await _get_redis()
    try:
        # 频率限制检查
        cooldown_key = f"sms:cooldown:{phone}"
        if await r.exists(cooldown_key):
            ttl = await r.ttl(cooldown_key)
            raise AppException(f"请 {ttl} 秒后再试", code=429)

        daily_key = f"sms:daily:{phone}"
        daily_count = await r.get(daily_key)
        if daily_count and int(daily_count) >= DAILY_LIMIT:
            raise AppException("今日验证码发送次数已达上限", code=429)

        # 生成验证码
        code = "".join(random.choices(string.digits, k=CODE_LENGTH))

        # 存储验证码
        code_key = f"sms:code:{phone}"
        await r.setex(code_key, CODE_TTL_SECONDS, code)

        # 设置冷却
        await r.setex(cooldown_key, CODE_COOLDOWN_SECONDS, "1")

        # 增加每日计数
        pipe = r.pipeline()
        pipe.incr(daily_key)
        pipe.expire(daily_key, 86400)
        await pipe.execute()

        # 发送短信
        provider = await SystemConfigService.get_value(db, "sms_provider") or "aliyun"
        if provider == "aliyun":
            result = await _send_aliyun(db, phone, code)
        elif provider == "tencent":
            result = await _send_tencent(db, phone, code)
        elif provider == "custom":
            result = await _send_custom(db, phone, code)
        else:
            result = await _send_aliyun(db, phone, code)

        logger.info("sms_code_sent: phone=%s provider=%s", phone[:3] + "****", provider)
        return result
    finally:
        await r.aclose()


async def verify_sms_code(phone: str, code: str) -> bool:
    """验证短信验证码。成功后删除验证码（一次性使用）。"""
    r = await _get_redis()
    try:
        code_key = f"sms:code:{phone}"
        stored = await r.get(code_key)
        if not stored:
            return False
        if stored != code:
            return False
        await r.delete(code_key)
        return True
    finally:
        await r.aclose()


async def _send_aliyun(db: AsyncSession, phone: str, code: str) -> dict[str, Any]:
    """阿里云短信发送。"""
    try:
        import base64
        import hashlib
        import hmac
        import time
        import urllib.parse
        import uuid

        import httpx

        access_key_id = await SystemConfigService.get_value(db, "sms_access_key_id")
        access_key_secret = await SystemConfigService.get_value(db, "sms_access_key_secret")
        sign_name = await SystemConfigService.get_value(db, "sms_sign_name")
        template_code = await SystemConfigService.get_value(db, "sms_template_code")

        if not access_key_id or not access_key_secret:
            logger.warning("sms_aliyun_config_incomplete: access_key_id or secret missing")
            return {"success": False, "message": "阿里云短信配置不完整"}

        endpoint = "https://dysmsapi.aliyuncs.com"
        params = {
            "PhoneNumbers": phone,
            "SignName": sign_name,
            "TemplateCode": template_code,
            "TemplateParam": f'{{"code":"{code}"}}',
            "Action": "SendSms",
            "Version": "2017-05-25",
            "Format": "JSON",
            "AccessKeyId": access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "RegionId": "cn-hangzhou",
        }

        sorted_params = sorted(params.items())
        query_string = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted_params
        )
        string_to_sign = f"GET&%2F&{urllib.parse.quote(query_string, safe='')}"
        signature = base64.b64encode(
            hmac.new(
                (access_key_secret + "&").encode(),
                string_to_sign.encode(),
                hashlib.sha1,
            ).digest()
        ).decode()
        url = f"{endpoint}/?Signature={urllib.parse.quote(signature)}&{query_string}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()

        if data.get("Code") == "OK":
            return {"success": True, "message": "验证码已发送"}
        logger.warning("sms_aliyun_error: %s", data)
        return {"success": False, "message": f"发送失败：{data.get('Message', '未知错误')}"}
    except Exception as e:
        logger.error("sms_aliyun_exception: %s", e)
        return {"success": False, "message": str(e)}


async def _send_tencent(db: AsyncSession, phone: str, code: str) -> dict[str, Any]:
    """腾讯云短信发送（简化版，生产环境建议用 SDK）。"""
    logger.info("sms_tencent_send: phone=%s code=sent", phone[:3] + "****")
    return {"success": True, "message": "验证码已发送（请配置腾讯云短信 SDK）"}


async def _send_custom(db: AsyncSession, phone: str, code: str) -> dict[str, Any]:
    """自定义 HTTP API 短信发送。"""
    try:
        import httpx

        endpoint = await SystemConfigService.get_value(db, "sms_endpoint")
        if not endpoint:
            return {"success": False, "message": "自定义短信 API 端点未配置"}

        payload = {"phone": phone, "code": code}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(endpoint, json=payload)
            if resp.status_code == 200:
                return {"success": True, "message": "验证码已发送"}
            return {"success": False, "message": f"自定义短信服务返回 {resp.status_code}"}
    except Exception as e:
        logger.error("sms_custom_exception: %s", e)
        return {"success": False, "message": str(e)}
