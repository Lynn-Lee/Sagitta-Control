from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.engines.models import ResultSet
from app.engines.oracle import OracleEngine
from app.services.session_diagnostic import is_collect_due, normalize_session_row


class _Instance(SimpleNamespace):
    id: int = 1
    instance_name: str = "prod"
    db_type: str = "mysql"
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "u"
    password: str = "p"
    db_name: str = ""


def test_normalize_mysql_processlist_row():
    inst = _Instance(db_type="mysql")
    item = normalize_session_row(
        instance=inst,
        columns=["ID", "USER", "HOST", "DB", "COMMAND", "TIME", "STATE", "INFO"],
        row=(12, "app", "10.0.0.1:55123", "orders", "Query", 8, "Sending data", "select * from t"),
    )

    assert item.session_id == "12"
    assert item.username == "app"
    assert item.host == "10.0.0.1:55123"
    assert item.db_name == "orders"
    assert item.command == "Query"
    assert item.time_seconds == 8
    assert item.duration_ms == 8000
    assert item.sql_text == "select * from t"


def test_normalize_session_row_prefers_millisecond_duration():
    inst = _Instance(db_type="pgsql")
    item = normalize_session_row(
        instance=inst,
        columns=["pid", "usename", "duration_ms", "query"],
        row=(10, "app", 358.7, "select 1"),
    )

    assert item.session_id == "10"
    assert item.duration_ms == 359
    assert item.time_seconds == 0


def test_normalize_session_row_converts_microseconds_and_decimal_seconds():
    inst = _Instance(db_type="clickhouse")
    item = normalize_session_row(
        instance=inst,
        columns=["query_id", "user", "duration_us", "query"],
        row=("q1", "app", 1250500, "select 1"),
    )
    decimal = normalize_session_row(
        instance=inst,
        columns=["query_id", "user", "elapsed_sec", "query"],
        row=("q2", "app", 0.42, "select 2"),
    )

    assert item.duration_ms == 1250
    assert item.time_seconds == 1
    assert decimal.duration_ms == 420
    assert decimal.time_seconds == 0


def test_session_collect_due_uses_instance_interval():
    now = datetime.now(UTC)

    assert is_collect_due(SimpleNamespace(is_enabled=True, collect_interval=60, last_collect_at=None), now)
    assert not is_collect_due(
        SimpleNamespace(is_enabled=True, collect_interval=60, last_collect_at=now - timedelta(seconds=30)),
        now,
    )
    assert is_collect_due(
        SimpleNamespace(is_enabled=True, collect_interval=60, last_collect_at=now - timedelta(seconds=60)),
        now,
    )
    assert not is_collect_due(
        SimpleNamespace(is_enabled=False, collect_interval=60, last_collect_at=now - timedelta(seconds=120)),
        now,
    )


def test_normalize_oracle_session_row_requires_serial():
    inst = _Instance(db_type="oracle")
    item = normalize_session_row(
        instance=inst,
        columns=["SESSION_ID", "SERIAL", "USERNAME", "HOST", "PROGRAM", "DB_NAME", "STATE", "TIME_SECONDS", "SQL_ID", "SQL_TEXT"],
        row=(123, 456, "HR", "client01", "JDBC", "HR", "ACTIVE", 33, "abc123", "select 1 from dual"),
    )

    assert item.session_id == "123"
    assert item.serial == "456"
    assert item.username == "HR"
    assert item.sql_id == "abc123"
    assert item.duration_ms == 33000


@pytest.mark.asyncio
async def test_oracle_processlist_uses_v_session_and_vsql(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
    calls: list[str] = []

    def fake_run(self, sql, params=None):
        calls.append(sql)
        return ResultSet(column_list=["SESSION_ID"], rows=[(1,)])

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.processlist()

    assert rs.is_success
    assert "FROM v$session s" in calls[0]
    assert "LEFT JOIN v$sql q" in calls[0]


@pytest.mark.asyncio
async def test_oracle_kill_uses_sid_and_serial(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
    calls: list[str] = []

    def fake_statement(self, sql, params=None):
        calls.append(sql)
        return ResultSet()

    monkeypatch.setattr(OracleEngine, "_run_statement_sync", fake_statement)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.kill_connection(123, serial=456)

    assert rs.is_success
    assert calls == ["ALTER SYSTEM KILL SESSION '123,456' IMMEDIATE"]


@pytest.mark.asyncio
async def test_oracle_ash_history_uses_available_duration_column(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
    calls: list[str] = []

    def fake_run(self, sql, params=None):
        calls.append(sql)
        if "WHERE 1 = 0" in sql:
            return ResultSet(column_list=["SAMPLE_TIME", "SESSION_ID", "TIME_WAITED"])
        return ResultSet(column_list=["DURATION_MS"], rows=[(25,)])

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.ash_history(source="ash")

    assert rs.is_success
    assert "TIME_WAITED" in calls[1]
    assert " AS duration_ms" in calls[1]


@pytest.mark.asyncio
async def test_oracle_awr_history_reports_missing_view_permission(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)

    def fake_run(self, sql, params=None):
        return ResultSet(error="ORA-00942: table or view does not exist")

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.ash_history(source="awr")

    assert "缺少 AWR 视图权限" in rs.error
