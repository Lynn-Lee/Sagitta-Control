"""TiDB engine.

TiDB reuses MySQL protocol connectivity, but keeps TiDB-specific diagnostics
inside its own engine entrypoint.
"""

from __future__ import annotations

from typing import Any

from app.engines.models import ResultSet
from app.engines.mysql import MysqlEngine


class TidbEngine(MysqlEngine):
    """TiDB database engine."""

    name = "TidbEngine"
    db_type = "tidb"

    async def processlist(
        self, command_type: str = "Query", **kwargs: Any
    ) -> ResultSet:
        cluster_sql = self._processlist_sql(
            table_name="information_schema.CLUSTER_PROCESSLIST",
            include_instance=True,
            command_type=command_type,
        )
        rs = await self.query(db_name="", sql=cluster_sql, limit_num=0)
        if rs.is_success:
            return rs

        fallback_sql = self._processlist_sql(
            table_name="information_schema.PROCESSLIST",
            include_instance=False,
            command_type=command_type,
        )
        fallback = await self.query(db_name="", sql=fallback_sql, limit_num=0)
        if fallback.is_success:
            fallback.warning = f"CLUSTER_PROCESSLIST 不可用，已降级为本节点 PROCESSLIST：{rs.error}"
            return fallback

        minimal_sql = self._processlist_sql(
            table_name="information_schema.PROCESSLIST",
            include_instance=False,
            include_tidb_columns=False,
            command_type=command_type,
        )
        minimal = await self.query(db_name="", sql=minimal_sql, limit_num=0)
        if minimal.is_success:
            minimal.warning = (
                "CLUSTER_PROCESSLIST 和 TiDB 扩展字段不可用，已降级为基础 PROCESSLIST："
                f"{rs.error or fallback.error}"
            )
            return minimal
        return fallback

    def _processlist_sql(
        self,
        *,
        table_name: str,
        include_instance: bool,
        include_tidb_columns: bool = True,
        command_type: str = "Query",
    ) -> str:
        instance_expr = "INSTANCE AS instance," if include_instance else "NULL AS instance,"
        tidb_columns = (
            """
              DIGEST AS digest,
              MEM AS mem,
              DISK AS disk,
              TxnStart AS txn_start,
              RESOURCE_GROUP AS resource_group
            """
            if include_tidb_columns
            else """
              NULL AS digest,
              NULL AS mem,
              NULL AS disk,
              NULL AS txn_start,
              NULL AS resource_group
            """
        )
        command_filter = ""
        if command_type and command_type != "ALL":
            command_filter = f" AND COMMAND = '{self.escape_string(command_type)}'"
        return f"""
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
              'processlist_time' AS duration_source,
              STATE AS state,
              INFO AS sql_text,
              {tidb_columns}
            FROM {table_name}
            WHERE 1 = 1
            {command_filter}
        """
