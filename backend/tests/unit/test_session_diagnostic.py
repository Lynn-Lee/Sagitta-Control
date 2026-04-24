from types import SimpleNamespace

import pytest

from app.engines.models import ResultSet
from app.engines.oracle import OracleEngine
from app.services.session_diagnostic import normalize_session_row


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
    assert item.sql_text == "select * from t"


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
