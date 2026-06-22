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
    previous_long_name = "".join(["矢准", "数据", "库安全", "管控", "平台"])
    assert payload["message"] == "Sagitta Control 矢准管控"
    assert previous_long_name not in payload["message"]


def test_openapi_title_uses_short_chinese_brand():
    previous_long_name = "".join(["矢准", "数据", "库安全", "管控", "平台"])
    assert app.title == "Sagitta Control — 矢准管控"
    assert previous_long_name not in app.title


@pytest.mark.asyncio
async def test_docs_available_in_dev(monkeypatch):
    """开发环境下 /docs 应该可访问。"""
    monkeypatch.setenv("APP_ENV", "development")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/docs")
    # 开发模式下返回 200
    assert response.status_code == 200
