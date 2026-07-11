"""TiDB 引擎。

TiDB 复用 MySQL 协议连接，但把 TiDB 专属诊断逻辑保留在独立引擎入口中。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.models import ResultSet
from app.engines.mysql import MysqlEngine


class TidbEngine(MysqlEngine):
    """TiDB 数据库引擎。"""

    name = "TidbEngine"
    db_type = "tidb"

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        """TiDB 8.x does not support MySQL's EXPLAIN FORMAT=JSON."""
        explain_sql = f"EXPLAIN {sql.strip().rstrip(';')}"
        return await self.query(db_name=db_name, sql=explain_sql, limit_num=1000)

    @staticmethod
    def _bounded_int(value: int, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _rows_to_dicts(rs: ResultSet) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rs.rows:
            if isinstance(row, dict):
                result.append({str(k): v for k, v in row.items()})
            elif rs.column_list:
                result.append(dict(zip(rs.column_list, row, strict=False)))
            else:
                result.append({"value": row})
        return result

    @staticmethod
    def _append_missing_group(raw: dict[str, Any], group: str, error: str) -> None:
        if not error:
            return
        missing = raw.setdefault("missing_groups", {})
        if isinstance(missing, dict):
            missing[group] = error

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @classmethod
    def _top_sql_time_filter(
        cls,
        column_name: str,
        *,
        window_minutes: int,
        start_time: Any | None,
        end_time: Any | None,
    ) -> tuple[str, int, str, str]:
        start = cls._coerce_datetime(start_time)
        end = cls._coerce_datetime(end_time)
        if start and end:
            if start.tzinfo:
                start = start.replace(tzinfo=None)
            if end.tzinfo:
                end = end.replace(tzinfo=None)
        if start and end and start < end:
            start_sql = start.strftime("%Y-%m-%d %H:%M:%S.%f")
            end_sql = end.strftime("%Y-%m-%d %H:%M:%S.%f")
            minutes = max(1, int((end - start).total_seconds() // 60) or 1)
            return (
                f"{column_name} >= '{start_sql}' AND {column_name} <= '{end_sql}'",
                minutes,
                start_sql,
                end_sql,
            )
        bounded_window = cls._bounded_int(
            window_minutes,
            default=30,
            minimum=1,
            maximum=1440,
        )
        return (
            f"{column_name} >= NOW() - INTERVAL {bounded_window} MINUTE",
            bounded_window,
            "",
            "",
        )

    async def processlist(
        self, command_type: str = "Query", **kwargs: Any
    ) -> ResultSet:
        cluster_sql, cluster_params = self._tidb_processlist_sql(
            table_name="information_schema.CLUSTER_PROCESSLIST",
            include_instance=True,
            command_type=command_type,
        )
        rs = await self.query(db_name="", sql=cluster_sql, parameters=cluster_params, limit_num=0)
        if rs.is_success:
            return rs

        fallback_sql, fallback_params = self._tidb_processlist_sql(
            table_name="information_schema.PROCESSLIST",
            include_instance=False,
            command_type=command_type,
        )
        fallback = await self.query(db_name="", sql=fallback_sql, parameters=fallback_params, limit_num=0)
        if fallback.is_success:
            fallback.warning = f"CLUSTER_PROCESSLIST 不可用，已降级为本节点 PROCESSLIST：{rs.error}"
            return fallback

        minimal_sql, minimal_params = self._tidb_processlist_sql(
            table_name="information_schema.PROCESSLIST",
            include_instance=False,
            include_tidb_columns=False,
            command_type=command_type,
        )
        minimal = await self.query(db_name="", sql=minimal_sql, parameters=minimal_params, limit_num=0)
        if minimal.is_success:
            minimal.warning = (
                "CLUSTER_PROCESSLIST 和 TiDB 扩展字段不可用，已降级为基础 PROCESSLIST："
                f"{rs.error or fallback.error}"
            )
            return minimal
        return fallback

    def _tidb_processlist_sql(
        self,
        *,
        table_name: str,
        include_instance: bool,
        include_tidb_columns: bool = True,
        command_type: str = "Query",
    ) -> tuple[str, dict[str, Any]]:
        instance_expr = "INSTANCE AS instance," if include_instance else "NULL AS instance,"
        tidb_columns = (
            """
              DIGEST AS sql_id,
              DIGEST AS digest,
              MEM AS mem,
              DISK AS disk,
              TxnStart AS txn_start,
              RESOURCE_GROUP AS resource_group
            """
            if include_tidb_columns
            else """
              NULL AS sql_id,
              NULL AS digest,
              NULL AS mem,
              NULL AS disk,
              NULL AS txn_start,
              NULL AS resource_group
            """
        )
        command_filter = ""
        params: dict[str, Any] = {}
        if command_type and command_type != "ALL":
            command_filter = " AND COMMAND = %(command_type)s"
            params["command_type"] = command_type
        sql = f"""
            SELECT
              {instance_expr}
              ID AS session_id,
              USER AS username,
              HOST AS host,
              DB AS db_name,
              COMMAND AS command,
              TIME AS time_seconds,
              TIME * 1000 AS state_duration_ms,
              TIME * 1000 AS duration_ms,
              CAST(NULL AS SIGNED) AS connection_age_ms,
              CASE
                WHEN COMMAND = 'Sleep' THEN NULL
                WHEN INFO IS NOT NULL THEN TIME * 1000
                ELSE NULL
              END AS active_duration_ms,
              CAST(NULL AS SIGNED) AS transaction_age_ms,
              'processlist_time' AS duration_source,
              STATE AS state,
              CAST(NULL AS CHAR) AS trx_state,
              INFO AS sql_text,
              {tidb_columns}
            FROM {table_name}
            WHERE 1 = 1
            {command_filter}
        """
        return sql, params

    async def collect_metrics(self) -> dict[str, Any]:
        """采集 TiDB 核心指标，并补充观测中心可直接展示的增强项。"""
        raw = await super().collect_metrics()
        if raw.get("error"):
            return raw

        waits_rs = await self.collect_waits()
        if waits_rs.is_success:
            wait_rows = self._rows_to_dicts(waits_rs)
            raw["blocking_sessions"] = [
                row for row in wait_rows if row.get("row_type") == "blocking_session"
            ]
            raw["long_transactions"] = [
                row for row in wait_rows if row.get("row_type") == "long_transaction"
            ]
            stats = raw.setdefault("stats", {})
            if isinstance(stats, dict):
                stats["lock_waits"] = len(raw["blocking_sessions"])
                stats["long_transactions"] = len(raw["long_transactions"])
        else:
            self._append_missing_group(raw, "tidb_waits", waits_rs.error)

        token_rs = await self.collect_token_usage()
        if token_rs.is_success:
            raw["token_usage"] = self._rows_to_dicts(token_rs)
        else:
            self._append_missing_group(raw, "tidb_token_usage", token_rs.error)

        top_sql_rs = await self.collect_top_sql(limit=20, window_minutes=30)
        if top_sql_rs.is_success:
            raw["top_sql"] = self._rows_to_dicts(top_sql_rs)
            if top_sql_rs.warning:
                raw["top_sql_warning"] = top_sql_rs.warning
        else:
            self._append_missing_group(raw, "tidb_top_sql", top_sql_rs.error)

        return raw

    async def collect_top_sql(
        self,
        limit: int = 20,
        window_minutes: int = 30,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        """采集 TiDB Top SQL，优先 statement summary，降级到 slow query。"""
        summary_rs = await self._collect_statement_summary_top_sql(
            limit=limit,
            window_minutes=window_minutes,
            min_duration_ms=0,
            start_time=start_time,
            end_time=end_time,
        )
        if summary_rs.is_success and summary_rs.rows:
            return summary_rs

        slow_rs = await self._collect_slow_query_top_sql(
            limit=limit,
            window_minutes=window_minutes,
            min_duration_ms=0,
            start_time=start_time,
            end_time=end_time,
        )
        if slow_rs.is_success:
            if summary_rs.error:
                slow_rs.warning = f"CLUSTER_STATEMENTS_SUMMARY 不可用，已降级为 CLUSTER_SLOW_QUERY：{summary_rs.error}"
            return slow_rs
        if summary_rs.error:
            slow_rs.error = (
                f"CLUSTER_STATEMENTS_SUMMARY 不可用：{summary_rs.error}; "
                f"CLUSTER_SLOW_QUERY 不可用：{slow_rs.error}"
            )
        return slow_rs

    async def collect_waits(self) -> ResultSet:
        """采集 TiDB 锁等待和长事务，保持观测中心 waits 接口的现有结构。"""
        sql = """
            WITH lock_waits AS (
              SELECT
                TRX_ID,
                CURRENT_HOLDING_TRX_ID,
                COUNT(*) AS key_count
              FROM information_schema.DATA_LOCK_WAITS
              GROUP BY TRX_ID, CURRENT_HOLDING_TRX_ID
            ),
            sessions AS (
              SELECT
                INSTANCE,
                ID,
                USER,
                HOST,
                DB,
                COMMAND,
                STATE,
                TIME,
                DIGEST,
                INFO
              FROM information_schema.CLUSTER_PROCESSLIST
            )
            SELECT *
            FROM (
              SELECT
                'blocking_session' AS row_type,
                COALESCE(blocked_sess.INSTANCE, blocker_sess.INSTANCE) AS instance,
                blocker.SESSION_ID AS blocking_session,
                blocked.SESSION_ID AS blocked_session,
                blocked.SESSION_ID AS session_id,
                COALESCE(blocked_sess.USER, blocked.USER) AS username,
                blocked_sess.HOST AS host,
                blocked_sess.DB AS db_name,
                blocked_sess.COMMAND AS command,
                blocked_sess.STATE AS state,
                TIMESTAMPDIFF(MICROSECOND, blocked.START_TIME, NOW(6)) DIV 1000 AS duration_ms,
                blocked_sess.TIME AS time_seconds,
                blocked.ID AS trx_id,
                blocker.ID AS holding_trx_id,
                lock_waits.key_count AS key_count,
                COALESCE(blocked_sess.DIGEST, blocked.CURRENT_SQL_DIGEST) AS sql_id,
                COALESCE(blocked_sess.INFO, blocked.CURRENT_SQL_DIGEST_TEXT) AS sql_text,
                blocked.START_TIME AS started_at
              FROM lock_waits
              JOIN information_schema.CLUSTER_TIDB_TRX blocked
                ON lock_waits.TRX_ID = blocked.ID
              JOIN information_schema.CLUSTER_TIDB_TRX blocker
                ON lock_waits.CURRENT_HOLDING_TRX_ID = blocker.ID
              LEFT JOIN sessions blocked_sess
                ON blocked.SESSION_ID = blocked_sess.ID
              LEFT JOIN sessions blocker_sess
                ON blocker.SESSION_ID = blocker_sess.ID
              UNION ALL
              SELECT
                'long_transaction' AS row_type,
                sess.INSTANCE AS instance,
                CAST(NULL AS SIGNED) AS blocking_session,
                CAST(NULL AS SIGNED) AS blocked_session,
                tx.SESSION_ID AS session_id,
                COALESCE(sess.USER, tx.USER) AS username,
                sess.HOST AS host,
                sess.DB AS db_name,
                sess.COMMAND AS command,
                sess.STATE AS state,
                TIMESTAMPDIFF(MICROSECOND, tx.START_TIME, NOW(6)) DIV 1000 AS duration_ms,
                sess.TIME AS time_seconds,
                tx.ID AS trx_id,
                CAST(NULL AS CHAR) AS holding_trx_id,
                CAST(NULL AS SIGNED) AS key_count,
                COALESCE(sess.DIGEST, tx.CURRENT_SQL_DIGEST) AS sql_id,
                COALESCE(sess.INFO, tx.CURRENT_SQL_DIGEST_TEXT) AS sql_text,
                tx.START_TIME AS started_at
              FROM information_schema.CLUSTER_TIDB_TRX tx
              LEFT JOIN sessions sess
                ON tx.SESSION_ID = sess.ID
              WHERE tx.START_TIME <= NOW(6) - INTERVAL 10 MINUTE
            ) AS wait_rows
            ORDER BY duration_ms DESC
            LIMIT 100
        """
        return await self.query(db_name="", sql=sql, limit_num=0)

    async def collect_token_usage(self) -> ResultSet:
        """采集 TiDB token-limit 使用率，作为 extra_metrics 的 TiDB 诊断补充。"""
        sql = """
            SELECT
              active.instance,
              active.active_sessions,
              active.sleep_sessions,
              active.total_sessions,
              token.token_limit,
              ROUND(COALESCE(active.active_sessions, 0) / NULLIF(token.token_limit, 0), 4) AS token_usage,
              ROUND(100 * COALESCE(active.active_sessions, 0) / NULLIF(token.token_limit, 0), 2) AS token_usage_pct
            FROM (
              SELECT
                INSTANCE AS instance,
                SUM(CASE WHEN COMMAND <> 'Sleep' THEN 1 ELSE 0 END) AS active_sessions,
                SUM(CASE WHEN COMMAND = 'Sleep' THEN 1 ELSE 0 END) AS sleep_sessions,
                COUNT(*) AS total_sessions
              FROM information_schema.CLUSTER_PROCESSLIST
              GROUP BY INSTANCE
            ) active
            JOIN (
              SELECT
                CONCAT(SUBSTRING_INDEX(status_cfg.INSTANCE, ':', 1), ':', status_cfg.VALUE) AS instance,
                CAST(limit_cfg.VALUE AS UNSIGNED) AS token_limit
              FROM information_schema.CLUSTER_CONFIG status_cfg
              JOIN information_schema.CLUSTER_CONFIG limit_cfg
                ON SUBSTRING_INDEX(status_cfg.INSTANCE, ':', 1) = SUBSTRING_INDEX(limit_cfg.INSTANCE, ':', 1)
              WHERE status_cfg.KEY = 'status.status-port'
                AND limit_cfg.KEY = 'token-limit'
            ) token
              ON active.instance = token.instance
            ORDER BY token_usage DESC, active.instance
        """
        return await self.query(db_name="", sql=sql, limit_num=0)

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
        window_minutes: int = 30,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        limit = self._bounded_int(limit, default=100, minimum=1, maximum=500)
        min_duration_ms = self._bounded_int(
            min_duration_ms,
            default=1000,
            minimum=0,
            maximum=86_400_000,
        )
        summary_rs = await self._collect_statement_summary_top_sql(
            limit=limit,
            window_minutes=window_minutes,
            min_duration_ms=min_duration_ms,
        )
        if summary_rs.is_success and summary_rs.rows:
            return summary_rs

        slow_rs = await self._collect_slow_query_top_sql(
            limit=limit,
            window_minutes=window_minutes,
            min_duration_ms=min_duration_ms,
        )
        if slow_rs.is_success and slow_rs.rows:
            if summary_rs.error:
                slow_rs.warning = f"CLUSTER_STATEMENTS_SUMMARY 不可用，已降级为 CLUSTER_SLOW_QUERY：{summary_rs.error}"
            return slow_rs

        min_seconds = min_duration_ms / 1000
        sql = f"""
            SELECT
              'tidb_statements' AS source,
              CONCAT('tidb:', ID, ':', IFNULL(DIGEST, '')) AS source_ref,
              DB AS db_name,
              INFO AS sql_text,
              TIME * 1000 AS duration_ms,
              USER AS username,
              HOST AS client_host,
              DIGEST AS digest,
              COMMAND AS command,
              STATE AS state
            FROM information_schema.CLUSTER_PROCESSLIST
            WHERE INFO IS NOT NULL
              AND TIME >= {min_seconds}
            ORDER BY TIME DESC
            LIMIT {limit}
        """
        rs = await self.query(db_name="", sql=sql, limit_num=0)
        if rs.is_success:
            warnings = []
            if summary_rs.error:
                warnings.append(f"CLUSTER_STATEMENTS_SUMMARY 不可用：{summary_rs.error}")
            if slow_rs.error:
                warnings.append(f"CLUSTER_SLOW_QUERY 不可用：{slow_rs.error}")
            if warnings:
                rs.warning = "；".join(warnings)
            return rs

        fallback_sql = f"""
            SELECT
              'tidb_statements' AS source,
              CONCAT('tidb:', ID) AS source_ref,
              DB AS db_name,
              INFO AS sql_text,
              TIME * 1000 AS duration_ms,
              USER AS username,
              HOST AS client_host,
              COMMAND AS command,
              STATE AS state
            FROM information_schema.PROCESSLIST
            WHERE INFO IS NOT NULL
              AND TIME >= {min_seconds}
            ORDER BY TIME DESC
            LIMIT {limit}
        """
        fallback = await self.query(db_name="", sql=fallback_sql, limit_num=0)
        if fallback.is_success:
            fallback.warning = f"CLUSTER_PROCESSLIST 不可用，已降级为本节点 PROCESSLIST：{rs.error}"
        return fallback

    async def _collect_statement_summary_top_sql(
        self,
        *,
        limit: int,
        window_minutes: int,
        min_duration_ms: int,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        limit = self._bounded_int(limit, default=20, minimum=1, maximum=500)
        time_filter, effective_window_minutes, range_start, range_end = self._top_sql_time_filter(
            "SUMMARY_BEGIN_TIME",
            window_minutes=window_minutes,
            start_time=start_time,
            end_time=end_time,
        )
        min_duration_ms = self._bounded_int(
            min_duration_ms,
            default=0,
            minimum=0,
            maximum=86_400_000,
        )
        sql = f"""
            WITH source_rows AS (
              SELECT
                'summary' AS summary_source,
                SUMMARY_BEGIN_TIME,
                SUMMARY_END_TIME,
                SCHEMA_NAME,
                DIGEST,
                DIGEST_TEXT,
                QUERY_SAMPLE_TEXT,
                PLAN_DIGEST,
                EXEC_COUNT,
                SUM_LATENCY,
                AVG_PROCESS_TIME,
                SUM_COP_TASK_NUM,
                AVG_PROCESSED_KEYS,
                AVG_TOTAL_KEYS,
                AVG_RESULT_ROWS
              FROM information_schema.CLUSTER_STATEMENTS_SUMMARY
              WHERE {time_filter}
                AND DIGEST IS NOT NULL
              UNION ALL
              SELECT
                'summary_history' AS summary_source,
                SUMMARY_BEGIN_TIME,
                SUMMARY_END_TIME,
                SCHEMA_NAME,
                DIGEST,
                DIGEST_TEXT,
                QUERY_SAMPLE_TEXT,
                PLAN_DIGEST,
                EXEC_COUNT,
                SUM_LATENCY,
                AVG_PROCESS_TIME,
                SUM_COP_TASK_NUM,
                AVG_PROCESSED_KEYS,
                AVG_TOTAL_KEYS,
                AVG_RESULT_ROWS
              FROM information_schema.CLUSTER_STATEMENTS_SUMMARY_HISTORY
              WHERE {time_filter}
                AND DIGEST IS NOT NULL
            ),
            sqlstat AS (
              SELECT
                DIGEST AS digest,
                MAX(SCHEMA_NAME) AS db_name,
                MAX(DIGEST_TEXT) AS digest_text,
                MAX(QUERY_SAMPLE_TEXT) AS sample_sql,
                MAX(PLAN_DIGEST) AS plan_digest,
                MIN(SUMMARY_BEGIN_TIME) AS first_seen,
                MAX(SUMMARY_END_TIME) AS last_seen,
                SUM(EXEC_COUNT) AS executions,
                SUM(SUM_LATENCY) AS elapsed_ns,
                SUM(AVG_PROCESS_TIME * EXEC_COUNT) AS cop_process_ns,
                SUM(SUM_COP_TASK_NUM) AS cop_task_count,
                SUM(AVG_PROCESSED_KEYS * EXEC_COUNT) AS processed_keys,
                SUM(AVG_TOTAL_KEYS * EXEC_COUNT) AS total_keys,
                SUM(AVG_RESULT_ROWS * EXEC_COUNT) AS result_rows
              FROM source_rows
              GROUP BY DIGEST
            ),
            totals AS (
              SELECT
                SUM(elapsed_ns) AS total_elapsed_ns,
                SUM(cop_process_ns) AS total_cop_process_ns,
                SUM(cop_task_count) AS total_cop_task_count,
                SUM(processed_keys) AS total_processed_keys,
                SUM(total_keys) AS total_total_keys,
                SUM(result_rows) AS total_result_rows
              FROM sqlstat
            )
            SELECT
              'tidb_statements' AS source,
              CONCAT('tidb:top_sql:', sqlstat.digest, ':', IFNULL(DATE_FORMAT(sqlstat.first_seen, '%Y%m%d%H%i'), 'window')) AS source_ref,
              sqlstat.db_name AS db_name,
              sqlstat.digest AS sql_id,
              sqlstat.digest AS digest,
              sqlstat.plan_digest AS plan_digest,
              COALESCE(NULLIF(sqlstat.sample_sql, ''), sqlstat.digest_text, '') AS sql_text,
              sqlstat.executions AS executions,
              ROUND(sqlstat.elapsed_ns / 1000000) AS elapsed_time_ms,
              ROUND(sqlstat.elapsed_ns / NULLIF(sqlstat.executions, 0) / 1000000) AS avg_elapsed_ms,
              ROUND(sqlstat.elapsed_ns / NULLIF(sqlstat.executions, 0) / 1000000) AS avg_duration_ms,
              ROUND(sqlstat.elapsed_ns / NULLIF(sqlstat.executions, 0) / 1000000) AS duration_ms,
              ROUND(sqlstat.cop_process_ns / NULLIF(sqlstat.executions, 0) / 1000000, 2) AS avg_cop_time_ms,
              ROUND(sqlstat.cop_task_count / NULLIF(sqlstat.executions, 0), 2) AS avg_request_count,
              ROUND(sqlstat.processed_keys / NULLIF(sqlstat.executions, 0), 2) AS avg_processed_keys,
              ROUND(sqlstat.total_keys / NULLIF(sqlstat.executions, 0), 2) AS avg_total_keys,
              ROUND(sqlstat.result_rows / NULLIF(sqlstat.executions, 0), 2) AS avg_result_rows,
              sqlstat.processed_keys AS rows_examined,
              sqlstat.result_rows AS rows_sent,
              sqlstat.first_seen AS occurred_at,
              sqlstat.last_seen AS last_seen,
              ROUND(100 * COALESCE(sqlstat.elapsed_ns, 0) / NULLIF(totals.total_elapsed_ns, 0), 0) AS ela_pct,
              ROUND(100 * COALESCE(sqlstat.cop_process_ns, 0) / NULLIF(totals.total_cop_process_ns, 0), 0) AS coptm_pct,
              ROUND(100 * COALESCE(sqlstat.cop_task_count, 0) / NULLIF(totals.total_cop_task_count, 0), 0) AS req_pct,
              ROUND(100 * COALESCE(sqlstat.processed_keys, 0) / NULLIF(totals.total_processed_keys, 0), 0) AS pkey_pct,
              ROUND(100 * COALESCE(sqlstat.total_keys, 0) / NULLIF(totals.total_total_keys, 0), 0) AS ttkey_pct,
              ROUND(100 * COALESCE(sqlstat.result_rows, 0) / NULLIF(totals.total_result_rows, 0), 0) AS result_row_pct,
              {effective_window_minutes} AS window_minutes,
              '{range_start}' AS date_start,
              '{range_end}' AS date_end
            FROM sqlstat
            CROSS JOIN totals
            WHERE sqlstat.executions > 0
              AND COALESCE(NULLIF(sqlstat.sample_sql, ''), sqlstat.digest_text, '') <> ''
              AND ROUND(sqlstat.elapsed_ns / NULLIF(sqlstat.executions, 0) / 1000000) >= {min_duration_ms}
            ORDER BY coptm_pct DESC, ela_pct DESC, elapsed_time_ms DESC
            LIMIT {limit}
        """
        return await self.query(db_name="", sql=sql, limit_num=0)

    async def _collect_slow_query_top_sql(
        self,
        *,
        limit: int,
        window_minutes: int,
        min_duration_ms: int,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        limit = self._bounded_int(limit, default=20, minimum=1, maximum=500)
        time_filter, effective_window_minutes, range_start, range_end = self._top_sql_time_filter(
            "TIME",
            window_minutes=window_minutes,
            start_time=start_time,
            end_time=end_time,
        )
        min_duration_ms = self._bounded_int(
            min_duration_ms,
            default=0,
            minimum=0,
            maximum=86_400_000,
        )
        min_duration_seconds = min_duration_ms / 1000
        sql = f"""
            WITH sqlstat AS (
              SELECT
                DIGEST AS digest,
                MAX(DB) AS db_name,
                MAX(Query) AS sample_sql,
                MAX(Plan_digest) AS plan_digest,
                MIN(TIME) AS first_seen,
                MAX(TIME) AS last_seen,
                COUNT(*) AS executions,
                SUM(Query_time) AS elapsed_seconds,
                SUM(Cop_time) AS cop_process_seconds,
                SUM(Request_count) AS request_count,
                SUM(Process_keys) AS processed_keys,
                SUM(Total_keys) AS total_keys,
                SUM(Result_rows) AS result_rows
              FROM information_schema.CLUSTER_SLOW_QUERY
              WHERE {time_filter}
                AND Query_time >= {min_duration_seconds}
                AND Query IS NOT NULL
                AND LOWER(Query) NOT LIKE 'analyze%'
                AND LOWER(Query) NOT LIKE 'alter%'
              GROUP BY DIGEST
            ),
            totals AS (
              SELECT
                SUM(elapsed_seconds) AS total_elapsed_seconds,
                SUM(cop_process_seconds) AS total_cop_process_seconds,
                SUM(request_count) AS total_request_count,
                SUM(processed_keys) AS total_processed_keys,
                SUM(total_keys) AS total_total_keys,
                SUM(result_rows) AS total_result_rows
              FROM sqlstat
            )
            SELECT
              'tidb_slow_query' AS source,
              CONCAT('tidb:slow_query:', IFNULL(sqlstat.digest, SHA1(sqlstat.sample_sql)), ':', IFNULL(DATE_FORMAT(sqlstat.first_seen, '%Y%m%d%H%i'), 'window')) AS source_ref,
              sqlstat.db_name AS db_name,
              sqlstat.digest AS sql_id,
              sqlstat.digest AS digest,
              sqlstat.plan_digest AS plan_digest,
              sqlstat.sample_sql AS sql_text,
              sqlstat.executions AS executions,
              ROUND(sqlstat.elapsed_seconds * 1000) AS elapsed_time_ms,
              ROUND(sqlstat.elapsed_seconds / NULLIF(sqlstat.executions, 0) * 1000) AS avg_elapsed_ms,
              ROUND(sqlstat.elapsed_seconds / NULLIF(sqlstat.executions, 0) * 1000) AS avg_duration_ms,
              ROUND(sqlstat.elapsed_seconds / NULLIF(sqlstat.executions, 0) * 1000) AS duration_ms,
              ROUND(sqlstat.cop_process_seconds / NULLIF(sqlstat.executions, 0) * 1000, 2) AS avg_cop_time_ms,
              ROUND(sqlstat.request_count / NULLIF(sqlstat.executions, 0), 2) AS avg_request_count,
              ROUND(sqlstat.processed_keys / NULLIF(sqlstat.executions, 0), 2) AS avg_processed_keys,
              ROUND(sqlstat.total_keys / NULLIF(sqlstat.executions, 0), 2) AS avg_total_keys,
              ROUND(sqlstat.result_rows / NULLIF(sqlstat.executions, 0), 2) AS avg_result_rows,
              sqlstat.processed_keys AS rows_examined,
              sqlstat.result_rows AS rows_sent,
              sqlstat.first_seen AS occurred_at,
              sqlstat.last_seen AS last_seen,
              ROUND(100 * COALESCE(sqlstat.elapsed_seconds, 0) / NULLIF(totals.total_elapsed_seconds, 0), 0) AS ela_pct,
              ROUND(100 * COALESCE(sqlstat.cop_process_seconds, 0) / NULLIF(totals.total_cop_process_seconds, 0), 0) AS coptm_pct,
              ROUND(100 * COALESCE(sqlstat.request_count, 0) / NULLIF(totals.total_request_count, 0), 0) AS req_pct,
              ROUND(100 * COALESCE(sqlstat.processed_keys, 0) / NULLIF(totals.total_processed_keys, 0), 0) AS pkey_pct,
              ROUND(100 * COALESCE(sqlstat.total_keys, 0) / NULLIF(totals.total_total_keys, 0), 0) AS ttkey_pct,
              ROUND(100 * COALESCE(sqlstat.result_rows, 0) / NULLIF(totals.total_result_rows, 0), 0) AS result_row_pct,
              {effective_window_minutes} AS window_minutes,
              '{range_start}' AS date_start,
              '{range_end}' AS date_end
            FROM sqlstat
            CROSS JOIN totals
            WHERE sqlstat.executions > 0
              AND sqlstat.sample_sql <> ''
            ORDER BY coptm_pct DESC, ela_pct DESC, elapsed_time_ms DESC
            LIMIT {limit}
        """
        return await self.query(db_name="", sql=sql, limit_num=0)
