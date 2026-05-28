"""
Text2SQL 服务：自然语言 → SQL 转换业务逻辑。
将 AI 调用、Prompt 构建、配置读取等逻辑与 HTTP 路由层解耦，
使该服务可被路由、Celery 任务、CLI 脚本等复用。
"""
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance import Instance
from app.services.system_config import SystemConfigService

logger = logging.getLogger(__name__)

_DIALECT_NAMES: dict[str, str] = {
    "mysql": "MySQL",
    "starrocks": "StarRocks",
    "pgsql": "PostgreSQL",
    "oracle": "Oracle",
    "mssql": "SQL Server",
    "clickhouse": "ClickHouse",
    "doris": "Doris",
}

_DEFAULT_PROVIDER = "anthropic"

_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "anthropic": {
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet-4-20250514",
    },
    "openai": {
        "protocol": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "protocol": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "qwen": {
        "protocol": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
    "minimax": {
        "protocol": "openai_compatible",
        "base_url": "https://api.minimax.io/v1",
        "model": "MiniMax-M2.7",
    },
    "xiaomi": {
        "protocol": "openai_compatible",
        "base_url": "",
        "model": "",
    },
    "custom": {
        "protocol": "openai_compatible",
        "base_url": "",
        "model": "",
    },
}


@dataclass
class AIConfig:
    provider: str
    protocol: str
    api_key: str
    model: str
    base_url: str


@dataclass
class Text2SQLResult:
    sql: str
    db_type: str
    model: str


async def generate_sql(
    db: AsyncSession,
    question: str,
    instance_id: int | None = None,
    db_name: str | None = None,
    dialect_hint: str | None = None,
) -> Text2SQLResult:
    """
    将自然语言转换为 SQL 语句。

    Args:
        db: 数据库会话（用于读取实例信息和系统配置）
        question: 自然语言描述
        instance_id: 可选，指定实例 ID 以推断方言
        db_name: 可选，数据库名，写入 Prompt 提升准确性
        dialect_hint: 可选，手动指定方言（优先级最低）

    Raises:
        ValueError: AI 功能未配置
        httpx.TimeoutException: AI API 请求超时
        RuntimeError: AI API 返回非 200 状态码
    """
    db_type = await _resolve_db_type(db, instance_id, dialect_hint)
    ai_config = await _load_ai_config(db)
    system_prompt = _build_system_prompt(db_type, db_name)
    user_message = f"请将以下需求转换为 {_DIALECT_NAMES.get(db_type, '标准SQL')} SQL：\n{question}"

    if ai_config.protocol == "anthropic":
        sql = await _call_anthropic_api(ai_config, system_prompt, user_message)
    else:
        sql = await _call_openai_compatible_api(ai_config, system_prompt, user_message)
    logger.info(
        "text2sql_success: db_type=%s provider=%s model=%s",
        db_type,
        ai_config.provider,
        ai_config.model,
    )
    return Text2SQLResult(sql=sql, db_type=db_type, model=ai_config.model)


async def _resolve_db_type(
    db: AsyncSession,
    instance_id: int | None,
    dialect_hint: str | None,
) -> str:
    """优先从实例记录推断方言，其次使用手动提示，最后默认 'sql'。"""
    if instance_id:
        result = await db.execute(select(Instance).where(Instance.id == instance_id))
        inst = result.scalar_one_or_none()
        if inst:
            return inst.db_type
    return dialect_hint or "sql"


async def _load_ai_config(db: AsyncSession) -> AIConfig:
    """从系统配置读取 AI 服务商、API Key、Base URL 和模型名称。"""
    enabled = await SystemConfigService.get_value(db, "ai_enabled")
    if enabled.lower() != "true":
        raise ValueError("AI 功能未启用，请先在系统配置中开启 AI 功能")

    provider = (await SystemConfigService.get_value(db, "ai_provider") or _DEFAULT_PROVIDER).lower()
    if provider not in _PROVIDER_PRESETS:
        raise ValueError(f"AI 模型服务商不支持：{provider}")
    preset = _PROVIDER_PRESETS[provider]

    api_key = await SystemConfigService.get_value(db, "ai_api_key")
    if not api_key:
        raise ValueError("AI 功能未配置，请在系统配置中设置 API Key")

    base_url = (await SystemConfigService.get_value(db, "ai_base_url") or preset["base_url"]).rstrip("/")
    model = await SystemConfigService.get_value(db, "ai_model") or preset["model"]
    if not base_url:
        raise ValueError("AI Base URL 未配置，请填写兼容 OpenAI 的 API Base URL")
    if not model:
        raise ValueError("AI 模型未配置，请填写模型 ID")

    return AIConfig(
        provider=provider,
        protocol=preset["protocol"],
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


def _build_system_prompt(db_type: str, db_name: str | None) -> str:
    dialect_name = _DIALECT_NAMES.get(db_type, "标准SQL")
    db_context = f"\n6. 当前数据库：{db_name}" if db_name else ""
    return (
        f"你是一个专业的数据库工程师，擅长将自然语言转换为精准的 {dialect_name} SQL 语句。\n\n"
        f"规则：\n"
        f"1. 只输出 SQL 语句，不要任何解释或 markdown 代码块标记\n"
        f"2. SQL 要符合 {dialect_name} 语法\n"
        f"3. 使用合理的表名和列名（如用户没有提供表结构，根据上下文推断）\n"
        f"4. 对于 DELETE/UPDATE 语句，必须包含 WHERE 条件\n"
        f"5. 适当添加 LIMIT 避免全表扫描"
        f"{db_context}"
    )


def _join_endpoint(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith(path):
        return base
    if path.startswith("/v1/") and base.endswith("/v1"):
        return base + path[3:]
    return base + path


async def _call_anthropic_api(
    config: AIConfig,
    system_prompt: str,
    user_message: str,
) -> str:
    """调用 Anthropic Messages API，返回清理后的 SQL 字符串。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _join_endpoint(config.base_url, "/v1/messages"),
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
        )

    if resp.status_code != 200:
        logger.error("anthropic_api_error: status=%s body=%s", resp.status_code, resp.text[:200])
        raise RuntimeError(f"AI API 调用失败：{resp.status_code}")

    return _strip_markdown_fences(_extract_anthropic_text(resp.json()))


async def _call_openai_compatible_api(
    config: AIConfig,
    system_prompt: str,
    user_message: str,
) -> str:
    """调用 OpenAI-compatible Chat Completions API，覆盖 OpenAI/DeepSeek/Qwen/MiniMax/自定义网关。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _join_endpoint(config.base_url, "/chat/completions"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "max_tokens": 1024,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
        )

    if resp.status_code != 200:
        logger.error(
            "openai_compatible_api_error: provider=%s status=%s body=%s",
            config.provider,
            resp.status_code,
            resp.text[:200],
        )
        raise RuntimeError(f"AI API 调用失败：{resp.status_code}")

    return _strip_markdown_fences(_extract_openai_compatible_text(resp.json()))


def _extract_anthropic_text(data: dict[str, Any]) -> str:
    content = data.get("content") or []
    if not content:
        raise RuntimeError("AI API 返回内容为空")
    first = content[0]
    text = str(first.get("text") or "").strip() if isinstance(first, dict) else str(first).strip()
    if not text:
        raise RuntimeError("AI API 返回内容为空")
    return text


def _extract_openai_compatible_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI API 返回内容为空")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        text = "".join(parts).strip()
    else:
        text = str(content).strip()
    if not text:
        raise RuntimeError("AI API 返回内容为空")
    return text


def _strip_markdown_fences(sql: str) -> str:
    """去除模型可能返回的 markdown 代码块标记。"""
    if not sql.startswith("```"):
        return sql
    lines = sql.split("\n")
    return "\n".join(line for line in lines if not line.startswith("```")).strip()
