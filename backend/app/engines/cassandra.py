"""Cassandra / ScyllaDB 引擎适配。

交付边界：连接测试、Keyspace/Table/Column 元数据、表 DDL、主键/索引元数据、
只读 SELECT 查询和基础健康指标。Cassandra/ScyllaDB 的 CQL 写入、DDL 和批量
变更语义与关系型工单差异较大，当前交付线保持工单执行 fail-close。
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host

if TYPE_CHECKING:
    from app.models.instance import Instance


_SYSTEM_KEYSPACES = {
    "system",
    "system_auth",
    "system_distributed",
    "system_schema",
    "system_traces",
    "system_views",
    "system_virtual_schema",
}
_WRITE_PREFIXES = {
    "alter",
    "batch",
    "call",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "revoke",
    "set",
    "truncate",
    "update",
    "use",
}


class CassandraEngine:
    name = "CassandraEngine"
    db_type = "cassandra"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._hosts = [
            normalize_engine_host(host.strip())
            for host in str(instance.host or "").split(",")
            if host.strip()
        ] or ["localhost"]
        self._port = instance.port or 9042
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._db_name = instance.db_name or None

    def _connect_sync(self, db_name: str | None = None) -> Any:
        try:
            from cassandra.auth import PlainTextAuthProvider
            from cassandra.cluster import Cluster
        except ImportError:
            raise ImportError("cassandra-driver 未安装，请先安装 backend 依赖") from None

        auth_provider = None
        if self._user or self._password:
            auth_provider = PlainTextAuthProvider(
                username=self._user or "",
                password=self._password or "",
            )
        cluster = Cluster(
            contact_points=self._hosts,
            port=self._port,
            auth_provider=auth_provider,
            connect_timeout=10,
            control_connection_timeout=10,
        )
        return cluster.connect(db_name or self._db_name)

    def _run_query_sync(
        self,
        sql: str,
        parameters: dict[str, Any] | tuple[Any, ...] | list[Any] | None = None,
        db_name: str | None = None,
    ) -> ResultSet:
        rs = ResultSet()
        session = None
        cluster = None
        start = time.monotonic()
        try:
            session = self._connect_sync(db_name)
            cluster = getattr(session, "cluster", None)
            result = session.execute(sql, parameters or None)
            rs.rows = [self._row_to_dict(row) for row in result.current_rows]
            rs.column_list = self._column_names(result, rs.rows)
            rs.affected_rows = len(rs.rows)
        except Exception as exc:
            rs.error = str(exc)
        finally:
            rs.cost_time = int((time.monotonic() - start) * 1000)
            if session is not None:
                session.shutdown()
            if cluster is not None:
                cluster.shutdown()
        return rs

    async def get_connection(self, db_name: str | None = None) -> Any:
        return await asyncio.to_thread(self._connect_sync, db_name)

    async def test_connection(self) -> ResultSet:
        return await asyncio.to_thread(
            self._run_query_sync,
            "SELECT release_version FROM system.local",
            None,
            None,
        )

    def escape_string(self, value: str) -> str:
        return value.replace("'", "''")

    async def get_all_databases(self) -> ResultSet:
        def load_keyspaces() -> ResultSet:
            rs = ResultSet(column_list=["keyspace_name"])
            session = None
            cluster: Any = None
            try:
                session = self._connect_sync(None)
                cluster = getattr(session, "cluster", None)
                keyspaces = sorted((cluster.metadata.keyspaces or {}).keys())
                rows = [(name,) for name in keyspaces if name not in _SYSTEM_KEYSPACES]
                rs.rows = rows
                rs.affected_rows = len(rows)
            except Exception as exc:
                rs.error = str(exc)
            finally:
                if session is not None:
                    session.shutdown()
                if cluster is not None:
                    cluster.shutdown()
            return rs

        return await asyncio.to_thread(load_keyspaces)

    async def get_all_tables(self, db_name: str, **kw: Any) -> ResultSet:
        def load_tables() -> ResultSet:
            rs = ResultSet(column_list=["table_name"])
            session = None
            cluster: Any = None
            try:
                session = self._connect_sync(db_name)
                cluster = getattr(session, "cluster", None)
                keyspace = (cluster.metadata.keyspaces or {}).get(db_name)
                if keyspace is None:
                    rs.error = f"Keyspace 不存在: {db_name}"
                    return rs
                rows = [(name,) for name in sorted((keyspace.tables or {}).keys())]
                rs.rows = rows
                rs.affected_rows = len(rows)
            except Exception as exc:
                rs.error = str(exc)
            finally:
                if session is not None:
                    session.shutdown()
                if cluster is not None:
                    cluster.shutdown()
            return rs

        return await asyncio.to_thread(load_tables)

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        def load_columns() -> ResultSet:
            rs = ResultSet(column_list=["column_name", "column_type", "kind", "position"])
            session = None
            cluster: Any = None
            try:
                session = self._connect_sync(db_name)
                cluster = getattr(session, "cluster", None)
                table = self._table_metadata(cluster, db_name, tb_name)
                if table is None:
                    rs.error = f"表不存在: {db_name}.{tb_name}"
                    return rs
                rows = []
                for idx, (name, column) in enumerate((table.columns or {}).items()):
                    kind = self._column_kind(table, name)
                    rows.append(
                        {
                            "column_name": name,
                            "column_type": str(getattr(column, "cql_type", None) or column),
                            "kind": kind,
                            "position": idx + 1,
                        }
                    )
                rs.rows = rows
                rs.affected_rows = len(rows)
            except Exception as exc:
                rs.error = str(exc)
            finally:
                if session is not None:
                    session.shutdown()
                if cluster is not None:
                    cluster.shutdown()
            return rs

        return await asyncio.to_thread(load_columns)

    async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        def load_ddl() -> ResultSet:
            session = None
            cluster: Any = None
            try:
                session = self._connect_sync(db_name)
                cluster = getattr(session, "cluster", None)
                table = self._table_metadata(cluster, db_name, tb_name)
                if table is None:
                    return ResultSet(error=f"表不存在: {db_name}.{tb_name}")
                ddl = table.export_as_string() if hasattr(table, "export_as_string") else str(table)
                return ResultSet(column_list=["ddl"], rows=[(ddl,)], affected_rows=1)
            except Exception as exc:
                return ResultSet(error=str(exc))
            finally:
                if session is not None:
                    session.shutdown()
                if cluster is not None:
                    cluster.shutdown()

        return await asyncio.to_thread(load_ddl)

    async def get_tables_metas_data(self, db_name: str, **kw: Any) -> list[dict[str, Any]]:
        rs = await self.get_all_tables(db_name)
        if not rs.is_success:
            return []
        return [{"table_name": self._first_value(row), "table_rows": None} for row in rs.rows]

    async def get_table_constraints(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        table_rs = await self._load_table_metadata(db_name, tb_name)
        if table_rs.error:
            return table_rs
        table = table_rs.rows[0]
        partition_keys = self._column_names_from_metadata(getattr(table, "partition_key", []))
        clustering_keys = self._column_names_from_metadata(getattr(table, "clustering_key", []))
        rows: list[dict[str, Any]] = []
        if partition_keys:
            rows.append(
                {
                    "constraint_name": f"{tb_name}_partition_key",
                    "constraint_type": "PARTITION KEY",
                    "column_names": ", ".join(partition_keys),
                    "referenced_table_name": "",
                    "referenced_column_names": "",
                    "check_clause": "",
                }
            )
        if clustering_keys:
            rows.append(
                {
                    "constraint_name": f"{tb_name}_clustering_key",
                    "constraint_type": "CLUSTERING KEY",
                    "column_names": ", ".join(clustering_keys),
                    "referenced_table_name": "",
                    "referenced_column_names": "",
                    "check_clause": "",
                }
            )
        return ResultSet(
            column_list=[
                "constraint_name",
                "constraint_type",
                "column_names",
                "referenced_table_name",
                "referenced_column_names",
                "check_clause",
            ],
            rows=rows,
            affected_rows=len(rows),
        )

    async def get_table_indexes(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet:
        table_rs = await self._load_table_metadata(db_name, tb_name)
        if table_rs.error:
            return table_rs
        table = table_rs.rows[0]
        partition_keys = self._column_names_from_metadata(getattr(table, "partition_key", []))
        clustering_keys = self._column_names_from_metadata(getattr(table, "clustering_key", []))
        rows: list[dict[str, Any]] = []
        if partition_keys:
            rows.append(
                {
                    "index_name": f"{tb_name}_partition_key",
                    "index_type": "PARTITION KEY",
                    "column_names": ", ".join(partition_keys),
                    "is_composite": "YES" if len(partition_keys) > 1 else "NO",
                    "index_comment": "Cassandra partition key",
                }
            )
        if clustering_keys:
            rows.append(
                {
                    "index_name": f"{tb_name}_clustering_key",
                    "index_type": "CLUSTERING KEY",
                    "column_names": ", ".join(clustering_keys),
                    "is_composite": "YES" if len(clustering_keys) > 1 else "NO",
                    "index_comment": "Cassandra clustering key",
                }
            )
        rows.extend(self._secondary_index_rows(table))
        return ResultSet(
            column_list=[
                "index_name",
                "index_type",
                "column_names",
                "is_composite",
                "index_comment",
            ],
            rows=rows,
            affected_rows=len(rows),
        )

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        result: dict[str, Any] = {"msg": "", "has_star": False, "syntax_error": False}
        sql_strip = sql.strip().rstrip(";")
        if not sql_strip:
            result["syntax_error"] = True
            result["msg"] = "CQL 不能为空"
            return result
        if self._has_extra_statement(sql):
            result["syntax_error"] = True
            result["msg"] = "Cassandra 查询接口不允许执行多语句"
            return result

        prefix = sql_strip.split(None, 1)[0].lower()
        result["has_star"] = bool(re.search(r"(?is)\bselect\s+\*", sql_strip))
        if prefix in _WRITE_PREFIXES:
            result["msg"] = f"Cassandra 查询接口不允许执行 {prefix.upper()} 操作"
            return result
        if prefix != "select":
            result["syntax_error"] = True
            result["msg"] = f"Cassandra 查询接口只允许 SELECT，不支持 {prefix.upper()} 语句"
            return result
        if re.search(r"(?is)\bselect\b.+\binto\b", sql_strip):
            result["syntax_error"] = True
            result["msg"] = "Cassandra 查询接口不允许 SELECT INTO 写入操作"
            return result
        if re.search(r"(?is)\bfor\s+update\b", sql_strip):
            result["syntax_error"] = True
            result["msg"] = "Cassandra 查询接口不允许锁定读"
            return result
        if not re.search(r"(?is)\bfrom\s+[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)?", sql_strip):
            result["syntax_error"] = True
            result["msg"] = "Cassandra SELECT 必须包含 FROM 表引用"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        sql_strip = sql.strip().rstrip(";")
        if (
            limit_num > 0
            and sql_strip.lower().startswith("select")
            and not re.search(r"\blimit\b", sql_strip, re.I)
        ):
            return f"{sql_strip} LIMIT {int(limit_num)}"
        return sql_strip

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | tuple[Any, ...] | list[Any] | None = None,
        **kw: Any,
    ) -> ResultSet:
        check = self.query_check(db_name, sql)
        if check["msg"] and (check["syntax_error"] or "不允许" in check["msg"]):
            return ResultSet(error=check["msg"])
        filtered_sql = self.filter_sql(sql, limit_num)
        return await asyncio.to_thread(self._run_query_sync, filtered_sql, parameters, db_name)

    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet:
        return resultset

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        review = ReviewSet(full_sql=sql)
        review.append(
            SqlItem(
                id=1,
                sql=sql,
                errlevel=2,
                stagestatus="Audit failed",
                errormessage="Cassandra 工单执行当前按交付边界关闭，仅开放只读 SELECT 在线查询",
            )
        )
        return review

    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet:
        return await self.execute_check(db_name, sql)

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        sql = workflow.content.sql_content if getattr(workflow, "content", None) else ""
        return await self.execute(getattr(workflow, "db_name", ""), sql)

    async def collect_metrics(self) -> dict[str, Any]:
        rs = await self._safe_query(
            "SELECT release_version, cluster_name, data_center FROM system.local"
        )
        peers_rs = await self._safe_query(
            "SELECT peer, data_center, rack, release_version FROM system.peers"
        )
        size_rs = await self._safe_query(
            """
            SELECT keyspace_name, table_name, range_start, range_end,
                   mean_partition_size, partitions_count
            FROM system.size_estimates
            LIMIT 50
            """
        )
        compaction_rs = await self._safe_query(
            """
            SELECT id, keyspace_name, columnfamily_name, compacted_at, bytes_in, bytes_out, rows_merged
            FROM system.compaction_history
            LIMIT 20
            """
        )
        first_row = rs.rows[0] if rs.is_success and rs.rows else {}
        version = str(self._dict_value(first_row, "release_version") or self._first_value(first_row) or "")
        cluster_name = str(self._dict_value(first_row, "cluster_name") or "")
        data_center = str(self._dict_value(first_row, "data_center") or "")
        size_rows = self._rows_to_dicts(size_rs)
        missing_groups = self._missing_groups(
            {
                "cassandra_local": rs,
                "cassandra_peers": peers_rs,
                "cassandra_size_estimates": size_rs,
                "cassandra_compaction_history": compaction_rs,
                "cassandra_jmx_metrics": ResultSet(
                    warning=(
                        "Cassandra 深度运行指标需要 JMX/sidecar 暴露，当前 CQL 账号仅采集系统表指标"
                    )
                ),
            }
        )
        metrics = {
            "health": {"up": 1 if rs.is_success else 0, "error": rs.error},
            "version": {"value": version},
            "cluster": {
                "name": cluster_name,
                "data_center": data_center,
                "peer_count": len(peers_rs.rows) if peers_rs.is_success else None,
                "peers": self._rows_to_dicts(peers_rs)[:20] if peers_rs.is_success else [],
            },
            "tables": {
                "estimated_partitions": sum(self._safe_int(row.get("partitions_count")) for row in size_rows),
                "estimated_bytes": sum(
                    self._safe_int(row.get("mean_partition_size"))
                    * self._safe_int(row.get("partitions_count"))
                    for row in size_rows
                ),
                "rows": size_rows[:50],
            },
            "compactions": {
                "recent_count": len(compaction_rs.rows) if compaction_rs.is_success else None,
                "rows": self._rows_to_dicts(compaction_rs)[:20]
                if compaction_rs.is_success
                else [],
            },
            "jmx_boundary": {
                "required_for": [
                    "read_write_latency",
                    "tombstone_scans",
                    "sstables",
                    "cache",
                    "thread_pools",
                    "repair",
                ],
                "status": "not_configured",
            },
        }
        if missing_groups:
            metrics["missing_groups"] = missing_groups
        return metrics

    def get_supported_metric_groups(self) -> list[str]:
        return [
            "health",
            "version",
            "cluster",
            "tables",
            "compactions",
            "jmx_boundary",
        ]

    async def _safe_query(
        self,
        sql: str,
        parameters: dict[str, Any] | tuple[Any, ...] | list[Any] | None = None,
    ) -> ResultSet:
        try:
            return await asyncio.to_thread(self._run_query_sync, sql, parameters, None)
        except Exception as exc:
            return ResultSet(error=str(exc))

    @classmethod
    def _rows_to_dicts(cls, rs: ResultSet) -> list[dict[str, Any]]:
        if not rs.is_success:
            return []
        return [cls._row_to_dict(row) for row in rs.rows]

    @staticmethod
    def _missing_groups(groups: dict[str, ResultSet]) -> dict[str, str]:
        missing: dict[str, str] = {}
        for name, rs in groups.items():
            if rs.error:
                missing[name] = rs.error
            elif rs.warning:
                missing[name] = rs.warning
        return missing

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        check = self.query_check(db_name, sql)
        if check["msg"]:
            return ResultSet(error=check["msg"])
        return ResultSet(
            warning="Cassandra/ScyllaDB CQL 不提供通用 EXPLAIN；请结合主键、二级索引和 tracing 在客户环境分析",
        )

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return {str(key): CassandraEngine._json_safe(value) for key, value in row.items()}
        if hasattr(row, "_asdict"):
            return {
                str(key): CassandraEngine._json_safe(value)
                for key, value in row._asdict().items()
            }
        if hasattr(row, "_fields"):
            return {
                str(field): CassandraEngine._json_safe(getattr(row, field))
                for field in row._fields
            }
        return {"value": CassandraEngine._json_safe(row)}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, UUID)):
            return str(value)
        if isinstance(value, dict):
            return {str(key): CassandraEngine._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [CassandraEngine._json_safe(item) for item in value]
        return str(value)

    @staticmethod
    def _column_names(result: Any, rows: list[dict[str, Any]]) -> list[str]:
        column_names = getattr(result, "column_names", None)
        if column_names:
            return list(column_names)
        if rows:
            return list(rows[0].keys())
        return []

    @staticmethod
    def _table_metadata(cluster: Any, db_name: str, tb_name: str) -> Any | None:
        metadata = getattr(cluster, "metadata", None)
        keyspaces = getattr(metadata, "keyspaces", {}) if metadata is not None else {}
        keyspace = (keyspaces or {}).get(db_name)
        if keyspace is None:
            return None
        return (keyspace.tables or {}).get(tb_name)

    async def _load_table_metadata(self, db_name: str, tb_name: str) -> ResultSet:
        def load_table() -> ResultSet:
            session = None
            cluster: Any = None
            try:
                session = self._connect_sync(db_name)
                cluster = getattr(session, "cluster", None)
                table = self._table_metadata(cluster, db_name, tb_name)
                if table is None:
                    return ResultSet(error=f"表不存在: {db_name}.{tb_name}")
                return ResultSet(rows=[table], affected_rows=1)
            except Exception as exc:
                return ResultSet(error=str(exc))
            finally:
                if session is not None:
                    session.shutdown()
                if cluster is not None:
                    cluster.shutdown()

        return await asyncio.to_thread(load_table)

    @staticmethod
    def _column_kind(table: Any, name: str) -> str:
        if name in [getattr(col, "name", col) for col in getattr(table, "partition_key", [])]:
            return "partition_key"
        if name in [getattr(col, "name", col) for col in getattr(table, "clustering_key", [])]:
            return "clustering_key"
        return "regular"

    @staticmethod
    def _column_names_from_metadata(columns: Any) -> list[str]:
        return [str(getattr(column, "name", column)) for column in columns or []]

    @staticmethod
    def _secondary_index_rows(table: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        indexes = getattr(table, "indexes", {}) or {}
        iterable: Any
        if isinstance(indexes, dict):
            iterable = indexes.items()
        else:
            iterable = [(getattr(index, "name", f"index_{idx}"), index) for idx, index in enumerate(indexes)]
        for name, index in iterable:
            column_names = CassandraEngine._index_column_names(index)
            rows.append(
                {
                    "index_name": str(getattr(index, "name", name)),
                    "index_type": str(getattr(index, "kind", "") or "SECONDARY INDEX"),
                    "column_names": ", ".join(column_names),
                    "is_composite": "YES" if len(column_names) > 1 else "NO",
                    "index_comment": str(getattr(index, "index_options", "") or ""),
                }
            )
        return rows

    @staticmethod
    def _index_column_names(index: Any) -> list[str]:
        for attr in ("columns", "column_names", "target"):
            value = getattr(index, attr, None)
            if not value:
                continue
            if isinstance(value, str):
                cleaned = value.strip('"')
                return [cleaned] if cleaned else []
            return [str(getattr(column, "name", column)).strip('"') for column in value]
        return []

    @staticmethod
    def _first_value(row: Any) -> Any:
        if isinstance(row, dict):
            return next(iter(row.values()), None)
        if isinstance(row, (tuple, list)):
            return row[0] if row else None
        return row

    @staticmethod
    def _dict_value(row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    @staticmethod
    def _has_extra_statement(sql: str) -> bool:
        text = sql.strip()
        if not text:
            return False
        in_single = False
        in_double = False
        escape = False
        for idx, char in enumerate(text):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                continue
            if char == ";" and not in_single and not in_double and text[idx + 1 :].strip():
                return True
        return False
