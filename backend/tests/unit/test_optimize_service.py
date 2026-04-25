from types import SimpleNamespace

import pytest

from app.schemas.optimize import OptimizeAnalyzeRequest
from app.services.optimize import OptimizeService


@pytest.mark.asyncio
async def test_optimize_service_returns_unsupported_for_non_sql_engine(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="redis", db_name="0")

    async def fake_resolve_input(db, user, data):
        return instance, "manual", "0", "get foo", {}

    monkeypatch.setattr(OptimizeService, "_resolve_input", fake_resolve_input)

    response = await OptimizeService.analyze(
        SimpleNamespace(),
        {"is_superuser": True},
        OptimizeAnalyzeRequest(instance_id=1, db_name="0", sql="get foo"),
    )

    assert response.supported is False
    assert response.support_level == "unsupported"
    assert response.engine == "redis"


@pytest.mark.asyncio
async def test_optimize_service_assembles_analyzer_response(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="mysql", db_name="app")

    async def fake_resolve_input(db, user, data):
        return instance, "manual", "app", "select * from users", {"duration_ms": 12000}

    class FakeAnalyzer:
        async def analyze(self):
            from app.schemas.optimize import OptimizeFinding, OptimizeMetadata, OptimizePlan, OptimizeRecommendation
            from app.services.optimize import AnalyzerResult

            return AnalyzerResult(
                support_level="full",
                findings=[
                    OptimizeFinding(
                        severity="critical",
                        code="FULL_SCAN",
                        title="存在全表扫描",
                        detail="计划显示全表扫描",
                    )
                ],
                recommendations=[
                    OptimizeRecommendation(
                        priority=1,
                        type="index",
                        title="检查索引",
                        action="评估过滤字段索引",
                    )
                ],
                plan=OptimizePlan(format="json", summary={"full_scan": True}),
                metadata=OptimizeMetadata(tables=["users"]),
                raw={"ok": True},
            )

    monkeypatch.setattr(OptimizeService, "_resolve_input", fake_resolve_input)
    monkeypatch.setattr("app.services.optimize.get_engine", lambda inst: SimpleNamespace())
    monkeypatch.setattr("app.services.optimize._analyzer_for", lambda inst, engine, db_name, sql: FakeAnalyzer())

    response = await OptimizeService.analyze(
        SimpleNamespace(),
        {"is_superuser": True},
        OptimizeAnalyzeRequest(instance_id=1, db_name="app", sql="select * from users"),
    )

    assert response.supported is True
    assert response.support_level == "full"
    assert response.risk_score >= 70
    assert response.metadata.slowlog["duration_ms"] == 12000
    assert response.recommendations[0].title == "检查索引"

