from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engines.models import ResultSet
from app.engines.mysql import MysqlEngine
from app.engines.oracle import OracleEngine
from app.engines.pgsql import PgSQLEngine
from app.engines.redis import RedisEngine
from app.engines.tidb import TidbEngine
from app.routers.diagnostic import _parse_oracle_dt
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
        columns=["pid", "usename", "connection_age_ms", "state_duration_ms", "active_duration_ms", "query"],
        row=(10, "app", 1000, 358.7, 200, "select 1"),
    )

    assert item.session_id == "10"
    assert item.duration_ms == 359
    assert item.connection_age_ms == 1000
    assert item.state_duration_ms == 359
    assert item.active_duration_ms == 200
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


@pytest.mark.asyncio
async def test_mysql_processlist_outputs_state_duration(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        return ResultSet()

    monkeypatch.setattr(MysqlEngine, "query", fake_query)
    engine = MysqlEngine(_Instance(db_type="mysql"))

    await engine.processlist(command_type="ALL")

    assert "p.TIME AS time_seconds" in calls[0]
    assert "p.TIME * 1000 AS state_duration_ms" in calls[0]
    assert "p.TIME * 1000 AS duration_ms" in calls[0]
    assert "CAST(NULL AS SIGNED) AS connection_age_ms" in calls[0]
    assert "performance_schema.threads" in calls[0]
    assert "performance_schema.events_statements_current" in calls[0]
    assert "information_schema.INNODB_TRX" in calls[0]
    assert "es.TIMER_WAIT" in calls[0]
    assert "TIMESTAMPDIFF(MICROSECOND, trx.TRX_STARTED, NOW(6)) DIV 1000" in calls[0]
    assert "p.COMMAND != 'Sleep'" not in calls[0]


@pytest.mark.asyncio
async def test_mysql_processlist_degrades_when_innodb_trx_unavailable(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        if "information_schema.INNODB_TRX" in sql:
            return ResultSet(error="access denied for INNODB_TRX")
        return ResultSet(column_list=["session_id"], rows=[{"session_id": 1}])

    monkeypatch.setattr(MysqlEngine, "query", fake_query)
    engine = MysqlEngine(_Instance(db_type="mysql"))

    rs = await engine.processlist(command_type="ALL")

    assert rs.is_success
    assert len(calls) == 2
    assert "information_schema.INNODB_TRX" in calls[0]
    assert "information_schema.INNODB_TRX" not in calls[1]
    assert "performance_schema.events_statements_current" in calls[1]
    assert "已降级采集" in rs.warning


@pytest.mark.asyncio
async def test_mysql_processlist_degrades_to_basic_processlist(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        if "performance_schema" in sql or "information_schema.INNODB_TRX" in sql:
            return ResultSet(error="permission denied")
        return ResultSet(column_list=["session_id"], rows=[{"session_id": 1}])

    monkeypatch.setattr(MysqlEngine, "query", fake_query)
    engine = MysqlEngine(_Instance(db_type="mysql"))

    rs = await engine.processlist(command_type="ALL")

    assert rs.is_success
    assert len(calls) == 4
    assert "performance_schema" not in calls[-1]
    assert "information_schema.INNODB_TRX" not in calls[-1]
    assert "CAST(NULL AS SIGNED) AS transaction_age_ms" in calls[-1]
    assert "'processlist_time' AS duration_source" in calls[-1]


@pytest.mark.asyncio
async def test_tidb_processlist_prefers_cluster_processlist(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        return ResultSet(column_list=["session_id"], rows=[(1,)])

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.processlist(command_type="ALL")

    assert rs.is_success
    assert "information_schema.CLUSTER_PROCESSLIST" in calls[0]
    assert "INSTANCE AS instance" in calls[0]
    assert "TIME * 1000 AS state_duration_ms" in calls[0]
    assert "TIME * 1000 AS duration_ms" in calls[0]
    assert "DIGEST AS sql_id" in calls[0]
    assert "active_duration_ms" in calls[0]
    assert "COMMAND != 'Sleep'" not in calls[0]


@pytest.mark.asyncio
async def test_tidb_processlist_falls_back_to_local_processlist(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        if "CLUSTER_PROCESSLIST" in sql:
            return ResultSet(error="access denied")
        return ResultSet(column_list=["session_id"], rows=[(1,)])

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.processlist(command_type="ALL")

    assert rs.is_success
    assert "information_schema.CLUSTER_PROCESSLIST" in calls[0]
    assert "information_schema.PROCESSLIST" in calls[1]
    assert "已降级为本节点 PROCESSLIST" in rs.warning


def test_normalize_tidb_processlist_row_exposes_tidb_fields():
    inst = _Instance(db_type="tidb")
    item = normalize_session_row(
        instance=inst,
        columns=[
            "instance",
            "session_id",
            "username",
            "sql_id",
            "digest",
            "mem",
            "disk",
            "txn_start",
            "resource_group",
            "sql_text",
        ],
        row=(
            "tidb85-tidb:10080",
            42,
            "app",
            "",
            "digest-1",
            2048,
            4096,
            "2026-05-14 10:00:00",
            "rg_app",
            "select 1",
        ),
    )

    assert item.tidb_instance == "tidb85-tidb:10080"
    assert item.sql_id == "digest-1"
    assert item.digest == "digest-1"
    assert item.mem_bytes == 2048
    assert item.disk_bytes == 4096
    assert item.txn_start == "2026-05-14 10:00:00"
    assert item.resource_group == "rg_app"


@pytest.mark.asyncio
async def test_tidb_collect_top_sql_uses_summary_history_and_fixed_percentages(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        return ResultSet(
            column_list=[
                "source",
                "source_ref",
                "executions",
                "elapsed_time_ms",
                "avg_elapsed_ms",
                "sql_text",
                "pkey_pct",
            ],
            rows=[
                {
                    "source": "tidb_statements",
                    "source_ref": "tidb:top_sql:d1:202605141000",
                    "executions": 3,
                    "elapsed_time_ms": 900,
                    "avg_elapsed_ms": 300,
                    "sql_text": "select * from t",
                    "pkey_pct": 29,
                }
            ],
        )

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.collect_top_sql(limit=7, window_minutes=30)

    assert rs.is_success
    assert rs.rows[0]["pkey_pct"] == 29
    assert "information_schema.CLUSTER_STATEMENTS_SUMMARY" in calls[0]
    assert "information_schema.CLUSTER_STATEMENTS_SUMMARY_HISTORY" in calls[0]
    assert "COALESCE(sqlstat.processed_keys, 0) / NULLIF(totals.total_processed_keys, 0)" in calls[0]
    assert "if(pkey is null" not in calls[0].lower()
    assert "LIMIT 7" in calls[0]


@pytest.mark.asyncio
async def test_tidb_collect_top_sql_falls_back_to_slow_query(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        if "CLUSTER_STATEMENTS_SUMMARY" in sql:
            return ResultSet()
        return ResultSet(
            column_list=["source", "sql_text", "avg_elapsed_ms"],
            rows=[{"source": "tidb_slow_query", "sql_text": "select slow", "avg_elapsed_ms": 1200}],
        )

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.collect_top_sql(limit=5)

    assert rs.is_success
    assert len(calls) == 2
    assert "information_schema.CLUSTER_SLOW_QUERY" in calls[1]
    assert "AND LOWER(Query) NOT LIKE 'analyze%'" in calls[1]
    assert "AND LOWER(Query) NOT LIKE 'alter%'" in calls[1]
    assert rs.rows[0]["source"] == "tidb_slow_query"


@pytest.mark.asyncio
async def test_tidb_collect_top_sql_accepts_custom_time_range(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        calls.append(sql)
        return ResultSet(
            column_list=["source", "sql_text", "window_minutes", "date_start", "date_end"],
            rows=[
                {
                    "source": "tidb_statements",
                    "sql_text": "select * from t",
                    "window_minutes": 45,
                    "date_start": "2026-05-14 10:00:00.000000",
                    "date_end": "2026-05-14 10:45:00.000000",
                }
            ],
        )

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.collect_top_sql(
        limit=5,
        start_time="2026-05-14 10:00:00",
        end_time="2026-05-14 10:45:00",
    )

    assert rs.is_success
    assert "SUMMARY_BEGIN_TIME >= '2026-05-14 10:00:00.000000'" in calls[0]
    assert "SUMMARY_BEGIN_TIME <= '2026-05-14 10:45:00.000000'" in calls[0]
    assert "45 AS window_minutes" in calls[0]


@pytest.mark.asyncio
async def test_tidb_collect_top_sql_reports_permission_fallback_errors(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)

    async def fake_query(self, db_name, sql, limit_num=0, parameters=None, **kwargs):
        if "CLUSTER_STATEMENTS_SUMMARY" in sql:
            return ResultSet(error="access denied for statement summary")
        return ResultSet(error="access denied for slow query")

    monkeypatch.setattr(TidbEngine, "query", fake_query)
    engine = TidbEngine(_Instance(db_type="tidb"))

    rs = await engine.collect_top_sql()

    assert not rs.is_success
    assert "CLUSTER_STATEMENTS_SUMMARY 不可用" in rs.error
    assert "CLUSTER_SLOW_QUERY 不可用" in rs.error


@pytest.mark.asyncio
async def test_tidb_collect_metrics_adds_enhanced_extra_metrics(monkeypatch):
    monkeypatch.setattr("app.engines.mysql.decrypt_field", lambda value: value)
    monkeypatch.setattr(
        MysqlEngine,
        "collect_metrics",
        AsyncMock(return_value={"health": {"up": 1}, "stats": {"qps": 1}}),
    )
    monkeypatch.setattr(
        TidbEngine,
        "collect_waits",
        AsyncMock(
            return_value=ResultSet(
                column_list=["row_type", "session_id"],
                rows=[
                    {"row_type": "blocking_session", "session_id": 10},
                    {"row_type": "long_transaction", "session_id": 11},
                ],
            )
        ),
    )
    monkeypatch.setattr(
        TidbEngine,
        "collect_token_usage",
        AsyncMock(
            return_value=ResultSet(
                column_list=["instance", "token_usage"],
                rows=[{"instance": "tidb:10080", "token_usage": 0.2}],
            )
        ),
    )
    monkeypatch.setattr(
        TidbEngine,
        "collect_top_sql",
        AsyncMock(
            return_value=ResultSet(
                column_list=["sql_text", "executions"],
                rows=[{"sql_text": "select 1", "executions": 1}],
            )
        ),
    )
    engine = TidbEngine(_Instance(db_type="tidb"))

    raw = await engine.collect_metrics()

    assert raw["blocking_sessions"] == [{"row_type": "blocking_session", "session_id": 10}]
    assert raw["long_transactions"] == [{"row_type": "long_transaction", "session_id": 11}]
    assert raw["token_usage"][0]["token_usage"] == 0.2
    assert raw["top_sql"][0]["sql_text"] == "select 1"
    assert raw["stats"]["lock_waits"] == 1
    assert raw["stats"]["long_transactions"] == 1


@pytest.mark.asyncio
async def test_pgsql_processlist_uses_state_change_for_duration(monkeypatch):
    monkeypatch.setattr("app.engines.pgsql.decrypt_field", lambda value: value)
    calls: list[str] = []

    async def fake_raw_query(self, db_name, sql, args):
        calls.append(sql)
        return ResultSet()

    monkeypatch.setattr(PgSQLEngine, "_raw_query", fake_raw_query)
    engine = PgSQLEngine(_Instance(db_type="pgsql", port=5432, db_name="postgres"))

    await engine.processlist()

    assert "now()-backend_start" in calls[0]
    assert "now()-state_change" in calls[0]
    assert "now()-query_start" in calls[0]


@pytest.mark.asyncio
async def test_redis_processlist_uses_client_list(monkeypatch):
    monkeypatch.setattr("app.engines.redis.decrypt_field", lambda value: value)

    class FakeRedis:
        async def client_list(self):
            return [
                {
                    "id": "7",
                    "addr": "10.0.0.8:51432",
                    "name": "worker",
                    "age": 15,
                    "idle": 3,
                    "db": 0,
                    "cmd": "get",
                    "flags": "N",
                    "user": "default",
                }
            ]

        async def aclose(self):
            return None

    async def fake_client(self, db_name=None):
        return FakeRedis()

    monkeypatch.setattr(RedisEngine, "_get_client", fake_client)
    engine = RedisEngine(_Instance(db_type="redis", port=6379, db_name="0"))

    rs = await engine.processlist(command_type="ALL")

    assert rs.is_success
    assert rs.column_list[:4] == ["session_id", "username", "host", "program"]
    assert rs.rows[0][0] == "7"
    assert rs.rows[0][2] == "10.0.0.8:51432"
    assert rs.rows[0][9] == 3000
    assert rs.rows[0][11] == "redis_client_list"


@pytest.mark.asyncio
async def test_redis_collect_metrics_maps_info_to_monitor_groups(monkeypatch):
    monkeypatch.setattr("app.engines.redis.decrypt_field", lambda value: value)

    class FakeRedis:
        async def info(self, section):
            assert section == "all"
            return {
                "redis_version": "7.2.0",
                "uptime_in_seconds": 3600,
                "connected_clients": 4,
                "blocked_clients": 1,
                "used_memory": 1024,
                "used_memory_peak": 2048,
                "maxmemory": 4096,
                "mem_fragmentation_ratio": 1.1,
                "total_commands_processed": 1200,
                "instantaneous_ops_per_sec": 12,
                "keyspace_hits": 90,
                "keyspace_misses": 10,
                "expired_keys": 2,
                "evicted_keys": 1,
                "rejected_connections": 3,
                "role": "master",
                "connected_slaves": 1,
            }

        async def aclose(self):
            return None

    async def fake_client(self, db_name=None):
        return FakeRedis()

    monkeypatch.setattr(RedisEngine, "_get_client", fake_client)
    engine = RedisEngine(_Instance(db_type="redis", port=6379, db_name="0"))

    metrics = await engine.collect_metrics()

    assert metrics["health"]["up"] == 1
    assert metrics["version"]["value"] == "7.2.0"
    assert metrics["connections"]["current"] == 4
    assert metrics["memory"]["memory_usage"] == 0.25
    assert metrics["stats"]["keyspace_hit_rate"] == 0.9
    assert metrics["stats"]["error_count"] == 3
    assert metrics["counters"]["queries"] == 1200
    assert metrics["replication"]["role"] == "master"


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
async def test_oracle_processlist_prefers_gv_session_process_and_sql(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
    calls: list[str] = []

    def fake_run(self, sql, params=None):
        calls.append(sql)
        return ResultSet(column_list=["SESSION_ID"], rows=[(1,)])

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.processlist()

    assert rs.is_success
    assert "FROM gv$session s" in calls[0]
    assert "LEFT JOIN gv$process p" in calls[0]
    assert "LEFT JOIN gv$sql q" in calls[0]
    assert "LEFT JOIN gv$transaction t" in calls[0]
    assert "s.inst_id AS inst_id" in calls[0]
    assert "p.spid AS process_id" in calls[0]
    assert "q.plan_hash_value AS plan_hash_value" in calls[0]
    assert "s.sql_plan_hash_value" not in calls[0]
    assert "s.wait_class AS wait_class" in calls[0]
    assert "s.blocking_instance AS blocking_instance" in calls[0]
    assert "p.pga_used_mem AS pga_used_mem" in calls[0]
    assert "SYSDATE - s.logon_time" in calls[0]
    assert "s.last_call_et * 1000 AS state_duration_ms" in calls[0]
    assert "SYSDATE - s.sql_exec_start" in calls[0]
    assert "s.last_call_et * 1000 AS duration_ms" in calls[0]


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
async def test_oracle_ash_history_uses_zero_duration_when_no_duration_columns(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
    calls: list[str] = []

    def fake_run(self, sql, params=None):
        calls.append(sql)
        if "WHERE 1 = 0" in sql:
            return ResultSet(column_list=["SAMPLE_TIME", "SESSION_ID", "SESSION_SERIAL#", "USER_ID"])
        return ResultSet(column_list=["DURATION_MS"], rows=[(0,)])

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.ash_history(source="awr")

    assert rs.is_success
    assert "0 AS duration_ms" in calls[1]


def test_parse_oracle_dt_converts_iso_timezone_to_naive_local_datetime():
    parsed = _parse_oracle_dt("2026-04-25T05:11:18.000Z")

    assert parsed is not None
    assert parsed.tzinfo is None


@pytest.mark.asyncio
async def test_oracle_awr_history_reports_missing_view_permission(monkeypatch):
    monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)

    def fake_run(self, sql, params=None):
        return ResultSet(error="ORA-00942: table or view does not exist")

    monkeypatch.setattr(OracleEngine, "_run_query_sync", fake_run)
    engine = OracleEngine(_Instance(db_type="oracle", port=1521, db_name="FREEPDB1"))

    rs = await engine.ash_history(source="awr")

    assert "缺少 AWR 视图权限" in rs.error
