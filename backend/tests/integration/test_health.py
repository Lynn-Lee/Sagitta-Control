"""
集成测试：API 健康检查端点。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.2.2"


@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Sagitta Control 矢准数据库安全管控平台"


def test_openapi_title_uses_short_chinese_brand():
    assert app.title == "Sagitta Control — 矢准数据库安全管控平台"


@pytest.mark.asyncio
async def test_docs_available_in_dev(monkeypatch):
    """开发环境下 /docs 应该可访问。"""
    monkeypatch.setenv("APP_ENV", "development")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/docs")
    # 开发模式下返回 200
    assert response.status_code == 200
