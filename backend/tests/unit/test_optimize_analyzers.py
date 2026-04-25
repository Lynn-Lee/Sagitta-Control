from types import SimpleNamespace

import pytest

from app.engines.models import ResultSet
from app.services.optimize import (
    BaseSqlAnalyzer,
    MssqlAnalyzer,
    MysqlAnalyzer,
    OracleAnalyzer,
    StarRocksAnalyzer,
    TidbAnalyzer,
)


def _instance(db_type: str = "mysql"):
    return SimpleNamespace(id=1, db_type=db_type, db_name="app")


def test_static_analyze_detects_basic_sql_risks():
    analyzer = BaseSqlAnalyzer(_instance(), None, "app", "select * from users where name like '%foo'")

    findings = analyzer.static_analyze()
    codes = {item.code for item in findings}

    assert "SELECT_STAR" in codes
    assert "LIKE_LEADING_WILDCARD" in codes
    assert "NO_LIMIT" in codes


def test_mysql_analyzer_detects_full_scan_and_sort():
    raw = {
        "query_block": {
            "table": {
                "access_type": "ALL",
                "rows_examined_per_scan": 200000,
                "using_filesort": True,
            }
        }
    }
    analyzer = MysqlAnalyzer(_instance("mysql"), None, "app", "select * from users")

    plan, findings = analyzer.parse_plan(raw)

    assert plan.summary["full_scan"] is True
    assert plan.summary["rows_estimate"] == 200000
    assert {item.code for item in findings} >= {"FULL_SCAN", "SORT"}


def test_tidb_analyzer_adds_native_table_full_scan_signal():
    raw = {"task": "cop[tikv]", "operator": "TableFullScan", "estRows": "10000"}
    analyzer = TidbAnalyzer(_instance("tidb"), None, "app", "select * from users")

    plan, findings = analyzer.parse_plan(raw)

    assert plan.summary["full_scan"] is True
    assert "cop[tikv]" in plan.summary["tasks"]
    assert any(item.code == "TABLE_FULL_SCAN" for item in findings)


def test_starrocks_analyzer_detects_exchange_and_distribution_strategy():
    raw = {
        "column_list": ["Explain String"],
        "rows": [[
            "0:OlapScanNode\n"
            "partitionRatio: 10/10, tabletRatio: 100/100\n"
            "1:EXCHANGE(BROADCAST)\n"
            "2:HASH JOIN"
        ]],
    }
    analyzer = StarRocksAnalyzer(_instance("starrocks"), None, "app", "select * from orders")

    plan, findings = analyzer.parse_plan(raw)

    assert plan.summary["scan_operator"] is True
    assert any(item.code == "DATA_EXCHANGE" for item in findings)
    assert any(item.code == "STARROCKS_JOIN_DISTRIBUTION" for item in findings)


def test_oracle_analyzer_detects_table_access_full():
    raw = {
        "column_list": ["PLAN_TABLE_OUTPUT"],
        "rows": [["|* 1 | TABLE ACCESS FULL | USERS | 100K |  1000 |"]],
    }
    analyzer = OracleAnalyzer(_instance("oracle"), None, "APP", "select * from users")

    plan, findings = analyzer.parse_plan(raw)

    assert plan.summary["full_scan"] is True
    assert any(item.code == "FULL_SCAN" for item in findings)


def test_mssql_analyzer_detects_missing_index_and_key_lookup():
    raw = {
        "column_list": ["Microsoft SQL Server 2005 XML Showplan"],
        "rows": [["<ShowPlanXML><MissingIndex /><RelOp PhysicalOp=\"Key Lookup\" /></ShowPlanXML>"]],
    }
    analyzer = MssqlAnalyzer(_instance("mssql"), None, "app", "select * from users")

    plan, findings = analyzer.parse_plan(raw)

    assert plan.format == "xml"
    codes = {item.code for item in findings}
    assert "MISSING_INDEX" in codes
    assert "KEY_LOOKUP" in codes


@pytest.mark.asyncio
async def test_mysql_analyzer_extracts_json_explain_value():
    class FakeEngine:
        async def explain_query(self, db_name: str, sql: str) -> ResultSet:
            return ResultSet(column_list=["EXPLAIN"], rows=[['{"query_block":{"table":{"access_type":"ALL"}}}']])

        async def get_table_indexes(self, db_name: str, tb_name: str) -> ResultSet:
            return ResultSet(column_list=["index_name"], rows=[("idx_users_id",)])

    analyzer = MysqlAnalyzer(_instance("mysql"), FakeEngine(), "app", "select * from users")

    result = await analyzer.analyze()

    assert result.support_level == "full"
    assert result.plan.summary["full_scan"] is True
    assert result.metadata.tables == ["users"]
    assert result.metadata.indexes[0]["index_name"] == "idx_users_id"

