from __future__ import annotations

from typing import Any

import pytest

from app.engines.models import ResultSet, ReviewSet
from app.engines.protocol import EngineProtocol


class MinimalEngine:
    name = "MinimalEngine"
    db_type = "minimal"

    async def get_connection(self, db_name: str | None = None) -> Any:
        return {"db_name": db_name}

    async def test_connection(self) -> ResultSet:
        return ResultSet()

    def escape_string(self, value: str) -> str:
        return value.replace("'", "''")

    async def get_all_databases(self) -> ResultSet:
        return ResultSet(rows=[{"name": "default"}])

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        return ResultSet(rows=[{"table_name": "users"}])

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        return ResultSet(rows=[{"column_name": "id"}])

    async def describe_table(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        return ResultSet(rows=[{"ddl": "CREATE TABLE users (id int)"}])

    async def get_tables_metas_data(self, db_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"table_name": "users"}]

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        return {"msg": "", "has_star": "*" in sql}

    def filter_sql(self, sql: str, limit_num: int) -> str:
        return f"{sql} LIMIT {limit_num}"

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        return ResultSet(rows=[parameters or {}])

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        return ReviewSet()

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        return ReviewSet()

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        return ReviewSet()


class DefaultEngine(MinimalEngine, EngineProtocol):
    pass


def test_engine_protocol_runtime_check_accepts_structural_engine() -> None:
    assert isinstance(DefaultEngine(), EngineProtocol)


@pytest.mark.asyncio
async def test_engine_protocol_default_optional_capabilities() -> None:
    engine = DefaultEngine()

    assert engine.auto_backup is False
    assert engine.server_version == ()
    assert await engine.get_rollback(object()) == []
    assert isinstance(await engine.get_table_constraints("db", "tb"), ResultSet)
    assert isinstance(await engine.get_table_indexes("db", "tb"), ResultSet)
    assert isinstance(await engine.processlist(), ResultSet)
    assert isinstance(await engine.kill_connection(123), ResultSet)
    assert isinstance(await engine.get_variables(["max_connections"]), ResultSet)
    assert isinstance(await engine.set_variable("max_connections", "100"), ResultSet)
    assert await engine.collect_metrics() == {"health": {"up": 0}}
    assert (await engine.collect_slow_queries()).warning == "minimal 暂不支持原生慢日志采集"
    assert (await engine.collect_sql_activity()).warning == "minimal 暂不支持 SQL 活动采集"
    assert (await engine.explain_query("db", "select 1")).warning == "minimal 暂不支持执行计划分析"
    assert engine.get_supported_metric_groups() == ["health"]
