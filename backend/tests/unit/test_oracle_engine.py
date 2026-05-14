"""
Oracle 引擎驱动模式测试。
"""

from types import SimpleNamespace

import pytest

import app.engines.oracle as oracle_module
from app.engines.models import ResultSet
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


class TestOracleExecution:
    def test_filter_sql_does_not_double_limit_existing_rownum_or_fetch(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())

        assert engine.filter_sql("SELECT * FROM users WHERE ROWNUM <= 5", 20) == (
            "SELECT * FROM users WHERE ROWNUM <= 5"
        )
        assert engine.filter_sql("SELECT * FROM users FETCH FIRST 5 ROWS ONLY", 20) == (
            "SELECT * FROM users FETCH FIRST 5 ROWS ONLY"
        )

    @pytest.mark.asyncio
    async def test_execute_uses_statement_runner_so_dml_commits(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        def fake_run_statement_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return ResultSet(affected_rows=3)

        monkeypatch.setattr(engine, "_run_statement_sync", fake_run_statement_sync)

        review = await engine.execute(
            "APP",
            "UPDATE users SET status = :status",
            parameters={"status": "active"},
        )

        assert captured == {
            "sql": "UPDATE users SET status = :status",
            "params": {"status": "active"},
        }
        assert review.is_executed is True
        assert review.rows[0].affected_rows == 3

    @pytest.mark.asyncio
    async def test_execute_workflow_reads_split_content(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        async def fake_execute(db_name, sql, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["kwargs"] = kwargs
            return ResultSet()

        monkeypatch.setattr(engine, "execute", fake_execute)
        workflow = SimpleNamespace(
            db_name="APP",
            content=SimpleNamespace(sql_content="UPDATE users SET status = 'active'"),
        )

        await engine.execute_workflow(workflow)

        assert captured == {
            "db_name": "APP",
            "sql": "UPDATE users SET status = 'active'",
            "kwargs": {},
        }


class TestOracleMonitoring:
    @pytest.mark.asyncio
    async def test_processlist_prefers_gv_session_process_sql(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return ResultSet(
                column_list=["session_id", "process_id"],
                rows=[(101, "12345")],
                affected_rows=1,
            )

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        rs = await engine.processlist()

        assert rs.is_success
        assert "FROM gv$session s" in str(captured["sql"])
        assert "gv$process p" in str(captured["sql"])
        assert "gv$sql q" in str(captured["sql"])
        assert "q.plan_hash_value AS plan_hash_value" in str(captured["sql"])
        assert "s.sql_plan_hash_value" not in str(captured["sql"])

    @pytest.mark.asyncio
    async def test_processlist_falls_back_to_v_session(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        calls: list[str] = []

        def fake_run_query_sync(sql, params=None):
            calls.append(str(sql))
            if "FROM gv$session s" in str(sql):
                return ResultSet(error="ORA-00942: table or view does not exist")
            return ResultSet(column_list=["session_id"], rows=[(102,)], affected_rows=1)

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        rs = await engine.processlist()

        assert rs.is_success
        assert "GV$ 会话视图不可用" in rs.warning
        assert "FROM v$session s" in calls[1]
        assert "q.plan_hash_value AS plan_hash_value" in calls[1]

    @pytest.mark.asyncio
    async def test_collect_sql_activity_uses_sql_monitor_first(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        captured: dict[str, object] = {}

        def fake_run_query_sync(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return ResultSet(
                column_list=["source", "source_ref", "sql_text", "duration_ms"],
                rows=[("oracle_sql_monitor", "oracle:sql_monitor:1:abc:9:20260514100000", "select 1", 1200)],
                affected_rows=1,
            )

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        rs = await engine.collect_sql_activity(limit=5, min_duration_ms=100, window_minutes=60)

        assert rs.is_success
        assert rs.rows[0][0] == "oracle_sql_monitor"
        assert "FROM gv$sql_monitor m" in str(captured["sql"])
        assert captured["params"]["limit"] == 5
        assert captured["params"]["window_minutes"] == 60

    @pytest.mark.asyncio
    async def test_collect_sql_activity_falls_back_to_awr_then_cursor_cache(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())
        calls: list[str] = []

        def fake_run_query_sync(sql, params=None):
            text = str(sql)
            calls.append(text)
            if "gv$sql_monitor" in text:
                return ResultSet(error="ORA-00942: no monitor")
            if "dba_hist_sqlstat" in text:
                return ResultSet(column_list=["source"], rows=[], affected_rows=0)
            return ResultSet(
                column_list=["source", "source_ref", "sql_text", "duration_ms"],
                rows=[("oracle_cursor_cache", "oracle:cursor_cache:1:def:123:202605141001", "select 2", 800)],
                affected_rows=1,
            )

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)

        rs = await engine.collect_sql_activity(limit=5, min_duration_ms=0)

        assert rs.is_success
        assert rs.rows[0][0] == "oracle_cursor_cache"
        assert "GV$SQL_MONITOR 不可用" in rs.warning
        assert any("dba_hist_sqlstat" in sql for sql in calls)
        assert any("FROM gv$sql" in sql for sql in calls)

    @pytest.mark.asyncio
    async def test_collect_sql_activity_last_resort_uses_session_activity(self, monkeypatch):
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        engine = OracleEngine(instance=MockOracleInstance())

        def fake_run_query_sync(sql, params=None):
            return ResultSet(error="ORA-00942: no privilege")

        async def fake_processlist(command_type="ALL"):
            return ResultSet(
                column_list=["session_id", "sql_id", "sql_text", "duration_ms", "username", "host"],
                rows=[(201, "abc", "select 3", 1500, "APP", "client")],
                affected_rows=1,
            )

        monkeypatch.setattr(engine, "_run_query_sync", fake_run_query_sync)
        monkeypatch.setattr(engine, "processlist", fake_processlist)

        rs = await engine.collect_sql_activity(limit=5, min_duration_ms=1000)

        assert rs.is_success
        assert rs.rows[0]["source"] == "oracle_activity"
        assert "已降级为当前会话 SQL 活动" in rs.warning
