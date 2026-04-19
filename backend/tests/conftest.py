"""
pytest 测试配置与公共 fixtures。

集成测试架构说明：
  每个测试的 client fixture 在当前 function-scoped event loop 内
  独立创建 AsyncEngine，彻底避免 asyncpg 连接跨 event loop 的问题。
  代价是每个集成测试会重建 schema（CREATE TABLE IF NOT EXISTS，幂等且快速）。
"""
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base

# 测试数据库 URL：只替换最后一段数据库名，保留用户名不变
_db_url_base, _, _ = settings.DATABASE_URL.rpartition("/")
TEST_DATABASE_URL = f"{_db_url_base}/sagittadb_test"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    每个测试独立创建 AsyncEngine + Session，与当前 event loop 严格绑定，
    避免 asyncpg 连接跨 loop 导致的 'Future attached to a different loop' 错误。
    """
    # 在当前 function loop 内创建 engine
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Clear all rows so each test starts with a fresh DB (handles cross-run persistence)
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.fixture
def mock_user():
    """模拟已登录用户。"""
    return {
        "id": 1,
        "username": "testuser",
        "display_name": "Test User",
        "is_superuser": False,
        "permissions": ["sql.sql_submit", "sql.query_submit"],
        "tenant_id": 1,
    }


@pytest.fixture
def mock_superuser():
    """模拟超级管理员。"""
    return {
        "id": 1,
        "username": "admin",
        "display_name": "Admin",
        "is_superuser": True,
        "permissions": [],
        "tenant_id": 1,
    }


# ── 集成测试辅助工具 ─────────────────────────────────────────

@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """
    返回管理员 Authorization 头，供集成测试使用。
    """
    await client.post("/api/v1/system/init/")
    resp = await client.post("/api/v1/auth/login/", json={
        "username": "admin", "password": "Admin@2024!",
    })
    assert resp.status_code == 200, f"初始化后仍无法登录: {resp.text}"
    data = resp.json()
    if data.get("password_change_required"):
        change_resp = await client.post("/api/v1/auth/password/change-required/", json={
            "password_change_token": data["password_change_token"],
            "new_password": "AdminReset@2026",
        })
        assert change_resp.status_code == 200, f"管理员改密失败: {change_resp.text}"
        resp = await client.post("/api/v1/auth/login/", json={
            "username": "admin", "password": "AdminReset@2026",
        })
        assert resp.status_code == 200, f"管理员改密后登录失败: {resp.text}"
        data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}
