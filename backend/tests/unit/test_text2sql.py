"""
Text2SQL 服务单元测试。
覆盖 AI 服务商配置读取、协议分发和响应解析。
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.text2sql import (
    AIConfig,
    _extract_anthropic_text,
    _extract_openai_compatible_text,
    _join_endpoint,
    _load_ai_config,
    generate_sql,
)


def _mock_config_getter(values: dict[str, str]):
    async def getter(_db, key: str) -> str:
        return values.get(key, "")

    return getter


@pytest.mark.asyncio
async def test_load_ai_config_rejects_disabled():
    with patch(
        "app.services.text2sql.SystemConfigService.get_value",
        side_effect=_mock_config_getter({"ai_enabled": "false"}),
    ), pytest.raises(ValueError, match="未启用"):
        await _load_ai_config(AsyncMock())


@pytest.mark.asyncio
async def test_load_ai_config_uses_openai_preset():
    values = {
        "ai_enabled": "true",
        "ai_provider": "openai",
        "ai_api_key": "sk-test",
        "ai_base_url": "",
        "ai_model": "",
    }
    with patch("app.services.text2sql.SystemConfigService.get_value", side_effect=_mock_config_getter(values)):
        config = await _load_ai_config(AsyncMock())

    assert config.provider == "openai"
    assert config.protocol == "openai_compatible"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_generate_sql_dispatches_openai_compatible_provider():
    config = AIConfig(
        provider="deepseek",
        protocol="openai_compatible",
        api_key="sk-test",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
    )
    with patch("app.services.text2sql._resolve_db_type", AsyncMock(return_value="mysql")), patch(
        "app.services.text2sql._load_ai_config",
        AsyncMock(return_value=config),
    ), patch(
        "app.services.text2sql._call_openai_compatible_api",
        AsyncMock(return_value="SELECT 1"),
    ) as call_openai:
        result = await generate_sql(AsyncMock(), question="查一条数据")

    assert result.sql == "SELECT 1"
    assert result.db_type == "mysql"
    assert result.model == "deepseek-chat"
    call_openai.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_sql_dispatches_anthropic_provider():
    config = AIConfig(
        provider="anthropic",
        protocol="anthropic",
        api_key="sk-ant-test",
        model="claude-sonnet-4-20250514",
        base_url="https://api.anthropic.com",
    )
    with patch("app.services.text2sql._resolve_db_type", AsyncMock(return_value="pgsql")), patch(
        "app.services.text2sql._load_ai_config",
        AsyncMock(return_value=config),
    ), patch(
        "app.services.text2sql._call_anthropic_api",
        AsyncMock(return_value="SELECT 1"),
    ) as call_anthropic:
        result = await generate_sql(AsyncMock(), question="查一条数据")

    assert result.sql == "SELECT 1"
    assert result.db_type == "pgsql"
    assert result.model == "claude-sonnet-4-20250514"
    call_anthropic.assert_awaited_once()


def test_join_endpoint_keeps_full_endpoint_and_v1_base():
    assert _join_endpoint("https://api.openai.com/v1", "/chat/completions") == (
        "https://api.openai.com/v1/chat/completions"
    )
    assert _join_endpoint("https://api.anthropic.com/v1", "/v1/messages") == (
        "https://api.anthropic.com/v1/messages"
    )
    assert _join_endpoint("https://proxy.example.com/v1/chat/completions", "/chat/completions") == (
        "https://proxy.example.com/v1/chat/completions"
    )


def test_extract_provider_responses():
    assert _extract_anthropic_text({"content": [{"text": "SELECT 1"}]}) == "SELECT 1"
    assert _extract_openai_compatible_text({"choices": [{"message": {"content": "SELECT 2"}}]}) == "SELECT 2"
