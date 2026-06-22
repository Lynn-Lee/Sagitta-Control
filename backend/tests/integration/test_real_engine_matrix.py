"""Optional real-service integration matrix for database engines.

These tests are skipped by default. Set SAGITTA_CONTROL_REAL_ENGINE_MATRIX_CONFIG to a
JSON file path to run them against customer-like database services.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.engines.registry import get_engine


def _load_cases() -> list[dict[str, Any]]:
    config_path = os.getenv("SAGITTA_CONTROL_REAL_ENGINE_MATRIX_CONFIG")
    if not config_path:
        return []
    path = Path(config_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("engines", [])
    if not isinstance(data, list):
        raise TypeError("SAGITTA_CONTROL_REAL_ENGINE_MATRIX_CONFIG must contain a list or {engines: []}")
    return data


CASES = _load_cases()
pytestmark = pytest.mark.skipif(
    not CASES,
    reason="Set SAGITTA_CONTROL_REAL_ENGINE_MATRIX_CONFIG to run real engine integration matrix",
)


def _instance_from_case(case: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=case.get("id", 1),
        instance_name=case.get("name", case["db_type"]),
        db_type=case["db_type"],
        host=case.get("host", "127.0.0.1"),
        port=case.get("port"),
        user=case.get("user", ""),
        password=case.get("password", ""),
        db_name=case.get("db_name", ""),
        sid=case.get("sid", ""),
        service_name=case.get("service_name", ""),
        role=case.get("role", ""),
        params=case.get("params", {}),
        show_db_name_regex=case.get("show_db_name_regex", ""),
        resource_groups=[],
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.get("name", case["db_type"]))
@pytest.mark.asyncio
async def test_real_engine_core_contract(case: dict[str, Any]) -> None:
    """Validate the common engine contract against a real database service."""
    instance = _instance_from_case(case)
    engine = get_engine(instance)
    db_name = case.get("db_name") or instance.db_name

    connection_rs = await engine.test_connection()
    assert connection_rs.is_success, connection_rs.error

    metrics = await engine.collect_metrics()
    assert metrics.get("health", {}).get("up") == 1, metrics

    if case.get("check_databases", True):
        databases_rs = await engine.get_all_databases()
        assert databases_rs.is_success, databases_rs.error

    table = case.get("table")
    if db_name and table:
        tables_rs = await engine.get_all_tables(db_name)
        assert tables_rs.is_success, tables_rs.error

        columns_rs = await engine.get_all_columns_by_tb(db_name, table)
        assert columns_rs.is_success, columns_rs.error
        assert columns_rs.affected_rows >= 1

        ddl_rs = await engine.describe_table(db_name, table)
        assert ddl_rs.is_success, ddl_rs.error

    query_sql = case.get("query")
    if db_name and query_sql:
        query_rs = await engine.query(
            db_name=db_name,
            sql=query_sql,
            limit_num=int(case.get("limit", 10)),
            parameters=case.get("parameters"),
        )
        assert query_rs.is_success, query_rs.error
        assert query_rs.affected_rows <= int(case.get("limit", 10))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.get("name", case["db_type"]))
@pytest.mark.asyncio
async def test_real_engine_write_boundary(case: dict[str, Any]) -> None:
    """Validate write execution boundaries when a case declares a write probe."""
    write_probe = case.get("write_probe")
    if not write_probe:
        pytest.skip("case does not declare write_probe")

    instance = _instance_from_case(case)
    engine = get_engine(instance)
    review = await engine.execute_check(case.get("db_name") or instance.db_name, write_probe["sql"])

    expected = write_probe.get("expected", "blocked")
    if expected == "blocked":
        assert review.error_count > 0 or review.error, review.to_dict()
    elif expected == "allowed":
        assert review.is_success, review.to_dict()
    else:
        raise ValueError(f"Unsupported write_probe.expected: {expected}")
