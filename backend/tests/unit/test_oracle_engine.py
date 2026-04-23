"""
Oracle 引擎驱动模式测试。
"""

from types import SimpleNamespace

import pytest

import app.engines.oracle as oracle_module
from app.engines.oracle import OracleEngine


class MockOracleInstance:
    host = "localhost"
    port = 1521
    user = ""
    password = ""
    db_name = "FREEPDB1"
    show_db_name_regex = ""


def _reset_oracle_client_state():
    oracle_module._ORACLE_CLIENT_INIT_ATTEMPTED = False
    oracle_module._ORACLE_CLIENT_INIT_ERROR = None


class TestOracleDriverMode:
    def test_connect_initializes_thick_mode_when_requested(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "thick")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        calls: list[tuple[str, dict]] = []

        def fake_init_oracle_client(**kwargs):
            calls.append(("init", kwargs))

        def fake_connect(**kwargs):
            calls.append(("connect", kwargs))
            return object()

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)
        monkeypatch.setattr(oracle_module.oracledb, "connect", fake_connect)

        engine = OracleEngine(instance=MockOracleInstance())
        conn = engine._connect_sync()

        assert conn is not None
        assert calls[0] == ("init", {})
        assert calls[1][0] == "connect"

    def test_auto_mode_falls_back_to_thin_when_thick_init_fails(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "auto")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        calls: list[str] = []

        def fake_init_oracle_client(**kwargs):
            calls.append("init")
            raise RuntimeError("DPI-1047: missing client")

        def fake_connect(**kwargs):
            calls.append("connect")
            return object()

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)
        monkeypatch.setattr(oracle_module.oracledb, "connect", fake_connect)

        engine = OracleEngine(instance=MockOracleInstance())
        conn = engine._connect_sync()

        assert conn is not None
        assert calls == ["init", "connect"]

    def test_thick_mode_raises_when_client_init_fails(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "thick")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        def fake_init_oracle_client(**kwargs):
            raise RuntimeError("DPI-1047: missing client")

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)

        engine = OracleEngine(instance=MockOracleInstance())

        try:
            engine._connect_sync()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected RuntimeError")

        assert "ORACLE_DRIVER_MODE=thick" in message
        assert "DPI-1047" in message


class _MockCursor:
    def __init__(self, ddl: str):
        self.ddl = ddl
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        return None

    def fetchone(self):
        return (self.ddl,)


class _MockConnection:
    def __init__(self, ddl: str):
        self.ddl = ddl

    def cursor(self):
        return _MockCursor(self.ddl)

    def close(self):
        return None


class TestOracleDDL:
    def test_get_table_ddl_uses_dbms_metadata(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        monkeypatch.setattr(engine, "_connect_sync", lambda: _MockConnection('CREATE TABLE "USERS" (\n  "ID" NUMBER\n);\n'))

        rs = engine._get_table_ddl_sync("demo", "users")

        assert rs.is_success
        assert rs.column_list == ["CREATE TABLE"]
        assert rs.rows == [('CREATE TABLE "USERS" (\n  "ID" NUMBER\n);',)]


class TestOracleMetadataQueries:
    @pytest.mark.asyncio
    async def test_get_all_columns_by_tb_queries_column_comments(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return SimpleNamespace(is_success=True, rows=[], column_list=[])

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        await engine.get_all_columns_by_tb("demo_schema", "users_demo")

        sql = str(captured["sql"])
        assert "FROM all_tab_columns c" in sql
        assert "LEFT JOIN all_col_comments cm" in sql
        assert captured["params"] == {"owner": "DEMO_SCHEMA", "table_name": "USERS_DEMO"}

    @pytest.mark.asyncio
    async def test_constraint_query_avoids_12c_only_search_condition_vc(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return SimpleNamespace(is_success=True, rows=[], column_list=[])

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        await engine.get_table_constraints("demo_schema", "users_demo")

        sql = str(captured["sql"])
        assert "SEARCH_CONDITION_VC" not in sql
        assert "'' AS check_clause" in sql
        assert captured["params"] == {"owner": "DEMO_SCHEMA", "table_name": "USERS_DEMO"}
