from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engines.models import ResultSet
from app.routers import slowlog as slowlog_router


@pytest.mark.asyncio
async def test_doris_realtime_sql_uses_processlist(monkeypatch):
    instance = SimpleNamespace(id=1, db_type="doris", db_name="warehouse")
    engine = SimpleNamespace(
        processlist=AsyncMock(
            return_value=ResultSet(
                column_list=["session_id", "time_seconds", "sql_text"],
                rows=[
                    {"session_id": 1, "time_seconds": 5, "sql_text": "select * from orders"},
                    {"session_id": 2, "time_seconds": 1, "sql_text": "select 1"},
                ],
            )
        )
    )
    monkeypatch.setattr(
        slowlog_router.SlowLogService,
        "get_instance_or_404",
        AsyncMock(return_value=instance),
    )
    monkeypatch.setattr(slowlog_router, "get_engine", lambda _instance: engine)

    result = await slowlog_router.list_slow_queries(
        instance_id=1,
        limit=50,
        min_seconds=2,
        user={"is_superuser": True},
        db=AsyncMock(),
    )

    engine.processlist.assert_awaited_once_with(command_type="ALL")
    assert result["total"] == 1
    assert result["items"][0]["session_id"] == 1


def test_row_duration_seconds_supports_doris_and_starrocks_shapes():
    assert slowlog_router._row_duration_seconds({"Time": "3"}) == 3
    assert slowlog_router._row_duration_seconds({"time_seconds": 4}) == 4
    assert slowlog_router._row_duration_seconds({"duration_ms": 2500}) == 2
    assert slowlog_router._row_duration_seconds({}) == 0
