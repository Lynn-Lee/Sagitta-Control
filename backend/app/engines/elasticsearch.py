"""Elasticsearch 引擎适配。

当前实现聚焦平台主链路：连接测试、索引元数据、SQL API 只读查询、
基础健康监控。写入、工单执行和归档仍交由原生生态能力处理。
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any

import sqlglot
import sqlglot.expressions as exp

from app.core.security import decrypt_field
from app.engines.models import ResultSet, ReviewSet, SqlItem
from app.engines.utils import normalize_engine_host, sanitize_sqlglot_error

if TYPE_CHECKING:
    from app.models.instance import Instance

_READ_PREFIXES = {"select", "with", "show", "desc", "describe", "explain"}
_WRITE_TYPES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable)


class ElasticsearchEngine:
    name = "ElasticsearchEngine"
    db_type = "elasticsearch"

    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self._host = normalize_engine_host(instance.host)
        self._port = instance.port
        self._user = decrypt_field(instance.user)
        self._password = decrypt_field(instance.password)
        self._client: Any | None = None

    async def get_connection(self, db_name: str | None = None) -> Any:
        if self._client is None:
            try:
                from elasticsearch import AsyncElasticsearch
            except ImportError as exc:
                raise ImportError("pip install 'elasticsearch[async]'") from exc

            url = self._connection_url()
            kwargs: dict[str, Any] = {
                "request_timeout": 10,
                "verify_certs": False,
                "ssl_show_warn": False,
            }
            if self._user or self._password:
                kwargs["basic_auth"] = (self._user, self._password)
            self._client = AsyncElasticsearch([url], **kwargs)
        return self._client

    def _connection_url(self) -> str:
        if self._host.startswith(("http://", "https://")):
            return self._host
        scheme = "https" if self._port == 443 else "http"
        return f"{scheme}://{self._host}:{self._port}"

    async def test_connection(self) -> ResultSet:
        try:
            client = await self.get_connection()
            info = self._to_plain(await client.info())
            version = (info.get("version") or {}).get("number", "")
            return ResultSet(
                column_list=["result", "cluster_name", "version"],
                rows=[("ok", info.get("cluster_name", ""), version)],
                affected_rows=1,
            )
        except Exception as exc:
            return ResultSet(error=str(exc))

    def escape_string(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("`", "\\`").replace('"', '\\"')

    async def get_all_databases(self) -> ResultSet:
        return await self._list_indices(self._index_pattern("*"))

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        return await self._list_indices(self._index_pattern(db_name or "*"))

    async def _list_indices(self, pattern: str) -> ResultSet:
        try:
            client = await self.get_connection()
            data = self._to_plain(
                await client.cat.indices(
                    index=pattern,
                    format="json",
                    h=["index", "health", "status", "docs.count", "store.size"],
                )
            )
            rows = [
                {
                    "index": item.get("index", ""),
                    "health": item.get("health", ""),
                    "status": item.get("status", ""),
                    "docs_count": item.get("docs.count", ""),
                    "store_size": item.get("store.size", ""),
                }
                for item in data
                if isinstance(item, dict) and item.get("index")
            ]
            if self.instance.show_db_name_regex:
                pattern_re = re.compile(self.instance.show_db_name_regex)
                rows = [row for row in rows if pattern_re.search(str(row["index"]))]
            return ResultSet(
                column_list=["index", "health", "status", "docs_count", "store_size"],
                rows=rows,
                affected_rows=len(rows),
            )
        except Exception as exc:
            return ResultSet(error=str(exc))

    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        mapping_rs = await self._get_mapping(tb_name or db_name)
        if mapping_rs.error:
            return mapping_rs
        rows: list[dict[str, Any]] = []
        for index_name, mapping in mapping_rs.rows:
            properties = (((mapping or {}).get("mappings") or {}).get("properties") or {})
            self._flatten_properties(rows, index_name, "", properties)
        return ResultSet(
            column_list=["index", "field", "type", "path"],
            rows=rows,
            affected_rows=len(rows),
        )

    async def describe_table(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        mapping_rs = await self._get_mapping(tb_name or db_name)
        if mapping_rs.error:
            return mapping_rs
        rows = [
            {"index": index_name, "mapping": json.dumps(mapping, ensure_ascii=False, sort_keys=True)}
            for index_name, mapping in mapping_rs.rows
        ]
        return ResultSet(column_list=["index", "mapping"], rows=rows, affected_rows=len(rows))

    async def _get_mapping(self, index: str) -> ResultSet:
        try:
            client = await self.get_connection()
            mapping = self._to_plain(await client.indices.get_mapping(index=self._index_pattern(index)))
            return ResultSet(rows=list(mapping.items()), affected_rows=len(mapping))
        except Exception as exc:
            return ResultSet(error=str(exc))

    @classmethod
    def _flatten_properties(
        cls,
        rows: list[dict[str, Any]],
        index_name: str,
        prefix: str,
        properties: dict[str, Any],
    ) -> None:
        for field_name, spec in properties.items():
            path = f"{prefix}.{field_name}" if prefix else field_name
            field_type = spec.get("type", "object") if isinstance(spec, dict) else "object"
            rows.append({"index": index_name, "field": field_name, "type": field_type, "path": path})
            nested = spec.get("properties") if isinstance(spec, dict) else None
            if isinstance(nested, dict):
                cls._flatten_properties(rows, index_name, path, nested)

    async def get_tables_metas_data(self, db_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        rs = await self.get_all_tables(db_name)
        return [row for row in rs.rows if isinstance(row, dict)] if rs.is_success else []

    async def get_table_constraints(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        return ResultSet(
            column_list=[
                "constraint_name",
                "constraint_type",
                "column_names",
                "referenced_table_name",
                "referenced_column_names",
                "check_clause",
            ],
            rows=[],
            affected_rows=0,
            warning=f"{self.db_type} 索引映射不提供关系型约束元数据",
        )

    async def get_table_indexes(self, db_name: str, tb_name: str, **kwargs: Any) -> ResultSet:
        columns_rs = await self.get_all_columns_by_tb(db_name, tb_name)
        if columns_rs.error:
            return columns_rs
        rows: list[dict[str, Any]] = []
        for row in columns_rs.rows:
            if not isinstance(row, dict):
                continue
            field_type = str(row.get("type") or "")
            path = str(row.get("path") or row.get("field") or "")
            if not path or field_type == "object":
                continue
            rows.append(
                {
                    "index_name": path,
                    "index_type": f"{field_type.upper()} FIELD",
                    "column_names": path,
                    "is_composite": "NO",
                    "index_comment": f"{self.db_type} mapping field",
                }
            )
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
            result["msg"] = "SQL 不能为空"
            return result

        prefix = sql_strip.split(None, 1)[0].lower()
        if prefix not in _READ_PREFIXES:
            result["msg"] = f"查询接口不允许执行 {prefix.upper()} 操作"
            return result
        if prefix in {"show", "desc", "describe"}:
            return result

        parse_sql = sql_strip
        if prefix == "explain":
            parse_sql = re.sub(r"^\s*explain\s+", "", sql_strip, count=1, flags=re.I)
        try:
            tree = sqlglot.parse_one(parse_sql, dialect="mysql")
        except sqlglot.errors.ParseError as exc:
            result["syntax_error"] = True
            result["msg"] = f"SQL 语法错误：{sanitize_sqlglot_error(str(exc))}"
            return result

        result["has_star"] = any(True for _ in tree.find_all(exp.Star))
        found_write = next((tree.find(wt) for wt in _WRITE_TYPES if tree.find(wt)), None)
        if found_write is not None:
            result["msg"] = f"查询接口不允许执行写操作：{type(found_write).__name__}"
        return result

    def filter_sql(self, sql: str, limit_num: int) -> str:
        if limit_num <= 0:
            return sql.strip().rstrip(";")
        sql_strip = sql.strip().rstrip(";")
        if sql_strip.lower().startswith(("select", "with")) and not re.search(
            r"\blimit\b", sql_strip, re.I
        ):
            return f"{sql_strip} LIMIT {int(limit_num)}"
        return sql_strip

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        rs = ResultSet()
        start = time.monotonic()
        try:
            client = await self.get_connection()
            limited_sql = self.filter_sql(sql, limit_num)
            payload: dict[str, Any] = {"query": limited_sql, "fetch_size": max(int(limit_num or 1000), 1)}
            if parameters:
                payload["params"] = list(parameters.values())
            data = self._to_plain(await self._sql_query(client, payload))
            columns = data.get("columns") or []
            rs.column_list = [col.get("name", "") for col in columns if isinstance(col, dict)]
            rs.rows = data.get("rows") or []
            rs.affected_rows = len(rs.rows)
        except Exception as exc:
            rs.error = str(exc)
        finally:
            rs.cost_time = int((time.monotonic() - start) * 1000)
        return rs

    async def _sql_query(self, client: Any, payload: dict[str, Any]) -> Any:
        return await client.sql.query(**payload)

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
                errormessage=f"{self.db_type} 工单执行暂不开放，请使用查询或原生生命周期管理能力",
            )
        )
        return review

    async def execute(self, db_name: str, sql: str, **kwargs: Any) -> ReviewSet:
        return await self.execute_check(db_name, sql)

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        sql = workflow.content.sql_content if getattr(workflow, "content", None) else ""
        return await self.execute(getattr(workflow, "db_name", ""), sql)

    async def collect_metrics(self) -> dict[str, Any]:
        try:
            client = await self.get_connection()
            health = self._to_plain(await client.cluster.health())
            info = self._to_plain(await client.info())
            indices = self._to_plain(
                await client.cat.indices(
                    index=self._index_pattern("*"),
                    format="json",
                    h=["index", "docs.count", "store.size"],
                )
            )
            index_count = len(indices) if isinstance(indices, list) else None
            docs_count = self._sum_int_field(indices, "docs.count")
            node_stats, node_error = await self._safe_call(
                lambda: client.nodes.stats(metric=["jvm", "thread_pool", "indices", "fs"])
            )
            thread_pool, thread_pool_error = await self._safe_call(
                lambda: client.cat.thread_pool(format="json")
            )
            shards, shards_error = await self._safe_call(
                lambda: client.cat.shards(format="json", h=["index", "shard", "prirep", "state", "node"])
            )
            segments, segments_error = await self._safe_call(
                lambda: client.cat.segments(format="json", h=["index", "shard", "segment", "docs.count", "size"])
            )
            metrics: dict[str, Any] = {
                "health": {"up": 1, "status": health.get("status", "")},
                "version": {"value": (info.get("version") or {}).get("number", "")},
                "cluster": {
                    "name": health.get("cluster_name", info.get("cluster_name", "")),
                    "nodes": health.get("number_of_nodes"),
                    "data_nodes": health.get("number_of_data_nodes"),
                    "active_shards": health.get("active_shards"),
                    "unassigned_shards": health.get("unassigned_shards"),
                },
                "indices": {
                    "count": index_count,
                    "docs_count": docs_count,
                    "active_primary_shards": health.get("active_primary_shards"),
                },
                "nodes": self._node_metrics(node_stats),
                "thread_pool": self._thread_pool_metrics(thread_pool),
                "shards": self._shard_metrics(shards),
                "segments": self._segment_metrics(segments),
            }
            missing_groups = {
                name: error
                for name, error in {
                    f"{self.db_type}_nodes": node_error,
                    f"{self.db_type}_thread_pool": thread_pool_error,
                    f"{self.db_type}_shards": shards_error,
                    f"{self.db_type}_segments": segments_error,
                }.items()
                if error
            }
            if missing_groups:
                metrics["missing_groups"] = missing_groups
            return metrics
        except Exception as exc:
            return {"health": {"up": 0, "error": str(exc)}}

    async def collect_slow_queries(
        self,
        since: Any | None = None,
        limit: int = 100,
        min_duration_ms: int = 1000,
    ) -> ResultSet:
        return ResultSet(warning=f"{self.db_type} 请通过 slowlog / audit log 原生能力采集慢查询")

    async def collect_sql_activity(
        self,
        limit: int = 100,
        min_duration_ms: int = 1000,
        window_minutes: int = 30,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> ResultSet:
        try:
            client = await self.get_connection()
            data = self._to_plain(
                await client.tasks.list(
                    actions=(
                        "indices:data/read/search*,"
                        "indices:data/read/async_search*,"
                        "cluster:monitor/xpack/sql*"
                    ),
                    detailed=True,
                )
            )
            rows = self._activity_rows_from_tasks(data, limit, min_duration_ms)
            return ResultSet(
                column_list=[
                    "source",
                    "source_ref",
                    "db_name",
                    "sql_text",
                    "duration_ms",
                    "username",
                    "client_host",
                    "command",
                    "state",
                ],
                rows=rows,
                affected_rows=len(rows),
            )
        except Exception as exc:
            return ResultSet(error=str(exc))

    async def explain_query(self, db_name: str, sql: str) -> ResultSet:
        return await self.query(db_name=db_name, sql=f"EXPLAIN {sql.strip().rstrip(';')}", limit_num=1)

    def get_supported_metric_groups(self) -> list[str]:
        return [
            "health",
            "cluster",
            "indices",
            "version",
            "nodes",
            "thread_pool",
            "shards",
            "segments",
        ]

    async def _safe_call(self, producer: Any) -> tuple[Any, str]:
        try:
            return self._to_plain(await producer()), ""
        except Exception as exc:
            return {}, str(exc)

    @staticmethod
    def _node_metrics(data: Any) -> dict[str, Any]:
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        heap_used = heap_max = disk_available = disk_total = 0
        rows = []
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            jvm_mem = ((node.get("jvm") or {}).get("mem") or {})
            fs_total = ((node.get("fs") or {}).get("total") or {})
            thread_pool = node.get("thread_pool") or {}
            indices = node.get("indices") or {}
            heap_used += int(jvm_mem.get("heap_used_in_bytes") or 0)
            heap_max += int(jvm_mem.get("heap_max_in_bytes") or 0)
            disk_available += int(fs_total.get("available_in_bytes") or 0)
            disk_total += int(fs_total.get("total_in_bytes") or 0)
            rows.append(
                {
                    "node_id": node_id,
                    "name": node.get("name", ""),
                    "heap_used_in_bytes": jvm_mem.get("heap_used_in_bytes"),
                    "heap_max_in_bytes": jvm_mem.get("heap_max_in_bytes"),
                    "segments_count": (indices.get("segments") or {}).get("count"),
                    "search_query_current": ((thread_pool.get("search") or {}).get("active")),
                    "search_rejected": ((thread_pool.get("search") or {}).get("rejected")),
                    "write_rejected": ((thread_pool.get("write") or {}).get("rejected")),
                }
            )
        return {
            "count": len(rows),
            "heap_usage": round(heap_used / heap_max, 4) if heap_max else None,
            "disk_usage": round((disk_total - disk_available) / disk_total, 4)
            if disk_total
            else None,
            "rows": rows,
        }

    @staticmethod
    def _thread_pool_metrics(rows: Any) -> dict[str, Any]:
        if not isinstance(rows, list):
            return {"rows": []}
        rejected = 0
        active = 0
        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            rejected += ElasticsearchEngine._safe_int(row.get("rejected"))
            active += ElasticsearchEngine._safe_int(row.get("active"))
            normalized.append(row)
        return {"active": active, "rejected": rejected, "rows": normalized[:40]}

    @staticmethod
    def _shard_metrics(rows: Any) -> dict[str, Any]:
        if not isinstance(rows, list):
            return {"rows": []}
        state_counts: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            state = str(row.get("state") or "UNKNOWN")
            state_counts[state] = state_counts.get(state, 0) + 1
        return {"count": len(rows), "state_counts": state_counts, "rows": rows[:50]}

    @staticmethod
    def _segment_metrics(rows: Any) -> dict[str, Any]:
        if not isinstance(rows, list):
            return {"rows": []}
        return {"count": len(rows), "rows": rows[:50]}

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _index_pattern(value: str) -> str:
        raw = (value or "*").strip()
        if not raw:
            return "*"
        if any(ch in raw for ch in "*?,"):
            return raw
        return raw if raw.startswith(".") else f"{raw}*"

    @staticmethod
    def _to_plain(response: Any) -> Any:
        if hasattr(response, "body"):
            return response.body
        return response

    @staticmethod
    def _sum_int_field(rows: Any, field: str) -> int | None:
        if not isinstance(rows, list):
            return None
        total = 0
        seen = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw = row.get(field)
            try:
                total += int(str(raw).replace(",", ""))
                seen = True
            except (TypeError, ValueError):
                continue
        return total if seen else None

    def _activity_rows_from_tasks(
        self,
        data: Any,
        limit: int,
        min_duration_ms: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
        for node_id, node in nodes.items():
            tasks = node.get("tasks", {}) if isinstance(node, dict) else {}
            for task_id, task in tasks.items():
                if not isinstance(task, dict):
                    continue
                duration_ms = int(float(task.get("running_time_in_nanos") or 0) / 1_000_000)
                if duration_ms < min_duration_ms:
                    continue
                headers = task.get("headers") or {}
                description = task.get("description") or task.get("action") or ""
                rows.append(
                    {
                        "source": f"{self.db_type}_activity",
                        "source_ref": str(task.get("id") or f"{node_id}:{task_id}"),
                        "db_name": "",
                        "sql_text": description,
                        "duration_ms": duration_ms,
                        "username": headers.get("es-security-runas-user")
                        or headers.get("user")
                        or "",
                        "client_host": headers.get("X-Forwarded-For") or "",
                        "command": task.get("action") or "",
                        "state": "running",
                    }
                )
        rows.sort(key=lambda item: int(item["duration_ms"]), reverse=True)
        return rows[: int(limit)]
