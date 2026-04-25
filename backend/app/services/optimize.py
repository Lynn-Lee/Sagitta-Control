"""SQL optimization v2 service and engine-specific analyzers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.engines.models import ResultSet
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.models.slowlog import SlowQueryLog
from app.schemas.optimize import (
    OptimizeAnalyzeRequest,
    OptimizeAnalyzeResponse,
    OptimizeFinding,
    OptimizeMetadata,
    OptimizePlan,
    OptimizeRecommendation,
    OptimizeSource,
    SupportLevel,
)
from app.services.slowlog import SlowLogService

_DIALECTS = {
    "mysql": "mysql",
    "tidb": "mysql",
    "starrocks": "mysql",
    "pgsql": "postgres",
    "postgres": "postgres",
    "postgresql": "postgres",
    "oracle": "oracle",
    "mssql": "tsql",
    "sqlserver": "tsql",
    "clickhouse": "clickhouse",
    "doris": "mysql",
}

_UNSUPPORTED_ENGINES = {"redis", "mongo", "mongodb", "elasticsearch", "opensearch", "cassandra"}
_PARTIAL_ENGINES = {"clickhouse", "doris"}
_DB_TYPE_LABELS = {
    "mysql": "MySQL",
    "tidb": "TiDB",
    "starrocks": "StarRocks",
    "pgsql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "oracle": "Oracle",
    "mssql": "MSSQL",
    "sqlserver": "MSSQL",
    "clickhouse": "ClickHouse",
    "doris": "Doris",
    "redis": "Redis",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "elasticsearch": "Elasticsearch",
    "opensearch": "OpenSearch",
    "cassandra": "Cassandra",
}


def _db_type_label(db_type: str | None) -> str:
    if not db_type:
        return "-"
    return _DB_TYPE_LABELS.get(db_type.lower(), db_type)


def _severity_score(severity: str) -> int:
    return {"critical": 28, "warning": 16, "info": 7, "ok": 0}.get(severity, 5)


def _row_to_dict(columns: list[str], row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if isinstance(row, (list, tuple)):
        return dict(zip(columns, row, strict=False))
    return {"value": row}


def _result_raw(rs: ResultSet) -> dict[str, Any]:
    return {
        "column_list": rs.column_list,
        "rows": [list(r) if isinstance(r, tuple) else r for r in rs.rows],
        "warning": rs.warning,
        "cost_time": rs.cost_time,
    }


def _first_value(rs: ResultSet) -> Any:
    if not rs.rows:
        return None
    row = rs.rows[0]
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return row


def _loads_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _walk_json_plan(node: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            nodes.extend(_walk_json_plan(item))
    elif isinstance(node, dict):
        nodes.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                nodes.extend(_walk_json_plan(value))
    return nodes


@dataclass
class AnalyzerResult:
    support_level: SupportLevel
    findings: list[OptimizeFinding] = field(default_factory=list)
    recommendations: list[OptimizeRecommendation] = field(default_factory=list)
    plan: OptimizePlan = field(default_factory=OptimizePlan)
    metadata: OptimizeMetadata = field(default_factory=OptimizeMetadata)
    raw: Any = None
    msg: str = ""


class BaseSqlAnalyzer:
    """Base analyzer: static SQL rules plus optional engine explain parsing."""

    engine_type = "generic"
    support_level: SupportLevel = "static_only"
    plan_format = "text"

    def __init__(self, instance: Instance, engine: Any, db_name: str, sql: str) -> None:
        self.instance = instance
        self.engine = engine
        self.db_name = db_name
        self.sql = sql.strip()
        self.dialect = _DIALECTS.get(instance.db_type, "mysql")

    async def analyze(self) -> AnalyzerResult:
        findings = self.static_analyze()
        raw: Any = None
        plan = OptimizePlan(format=self.plan_format, summary=self.empty_plan_summary())
        support_level = self.support_level
        msg = ""

        if support_level in {"full", "partial"} and self._is_explain_safe():
            rs = await self.explain()
            if rs.error:
                msg = rs.error
                support_level = "static_only" if self.support_level == "full" else self.support_level
            else:
                raw = self.extract_raw(rs)
                parsed_plan, plan_findings = self.parse_plan(raw)
                plan = parsed_plan
                findings.extend(plan_findings)
        elif support_level in {"full", "partial"}:
            msg = "仅支持 SELECT/WITH 查询的执行计划分析，已返回静态规则诊断"
            support_level = "static_only"

        metadata = await self.metadata_probe()
        recommendations = self.recommend(findings, plan, metadata)
        return AnalyzerResult(
            support_level=support_level,
            findings=findings,
            recommendations=recommendations,
            plan=plan,
            metadata=metadata,
            raw=raw,
            msg=msg,
        )

    def _is_explain_safe(self) -> bool:
        text = self.sql.lstrip().lower()
        return text.startswith("select ") or text.startswith("with ")

    def static_analyze(self) -> list[OptimizeFinding]:
        findings: list[OptimizeFinding] = []
        try:
            tree = sqlglot.parse_one(self.sql.rstrip(";"), dialect=self.dialect)
        except sqlglot.errors.ParseError as exc:
            return [
                OptimizeFinding(
                    severity="critical",
                    code="PARSE_ERROR",
                    title="SQL 解析失败",
                    detail=f"无法按 {self.dialect} 方言解析 SQL：{exc}",
                    confidence=0.95,
                )
            ]

        if tree.find(exp.Star):
            findings.append(OptimizeFinding(
                severity="warning",
                code="SELECT_STAR",
                title="返回列过宽",
                detail="查询使用 SELECT *，会增加网络传输、解码和脱敏成本。",
                evidence="SELECT *",
                confidence=0.9,
            ))

        if isinstance(tree, (exp.Update, exp.Delete)) and not tree.find(exp.Where):
            findings.append(OptimizeFinding(
                severity="critical",
                code="NO_WHERE",
                title="写操作缺少 WHERE",
                detail="UPDATE/DELETE 没有过滤条件，可能导致全表更新或删除。",
                evidence=tree.key.upper(),
                confidence=0.98,
            ))

        if isinstance(tree, exp.Select) and not tree.find(exp.Limit):
            findings.append(OptimizeFinding(
                severity="info",
                code="NO_LIMIT",
                title="查询未限制结果集",
                detail="SELECT 未包含 LIMIT/TOP/FETCH，交互式查询可能返回过多数据。",
                confidence=0.75,
            ))

        for like in tree.find_all(exp.Like):
            pattern = str(like.right)
            if pattern.startswith("'%") or pattern.startswith("'_"):
                findings.append(OptimizeFinding(
                    severity="warning",
                    code="LIKE_LEADING_WILDCARD",
                    title="LIKE 前导通配符",
                    detail="前导通配符通常无法利用普通 B-Tree 索引。",
                    evidence=pattern,
                    confidence=0.85,
                ))

        joins = list(tree.find_all(exp.Join))
        for join in joins:
            if not join.args.get("on") and not join.args.get("using"):
                findings.append(OptimizeFinding(
                    severity="warning",
                    code="JOIN_WITHOUT_CONDITION",
                    title="JOIN 缺少连接条件",
                    detail="JOIN 未发现 ON/USING 条件，可能产生笛卡尔积。",
                    evidence=str(join)[:180],
                    confidence=0.8,
                ))

        if len(list(tree.find_all(exp.Subquery))) > 2:
            findings.append(OptimizeFinding(
                severity="info",
                code="DEEP_SUBQUERY",
                title="子查询层级较深",
                detail="多层子查询可能影响可读性和优化器改写空间，可评估 CTE 或 JOIN。",
                confidence=0.65,
            ))

        if not findings:
            findings.append(OptimizeFinding(
                severity="ok",
                code="STATIC_PASS",
                title="静态规则未发现明显风险",
                detail="SQL 未命中内置静态高风险规则，仍建议结合执行计划判断。",
                confidence=0.6,
            ))
        return findings

    async def explain(self) -> ResultSet:
        return ResultSet(warning=f"{_db_type_label(self.engine_type)} 暂不支持执行计划分析")

    def extract_raw(self, rs: ResultSet) -> Any:
        return _result_raw(rs)

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        return OptimizePlan(format=self.plan_format, summary=self.empty_plan_summary()), []

    def empty_plan_summary(self) -> dict[str, Any]:
        return {
            "full_scan": False,
            "rows_estimate": 0,
            "max_cost": 0,
            "join_types": [],
            "sort": False,
            "temporary": False,
        }

    def extract_tables(self) -> list[str]:
        try:
            tree = sqlglot.parse_one(self.sql.rstrip(";"), dialect=self.dialect)
        except sqlglot.errors.ParseError:
            return []
        tables = []
        for table in tree.find_all(exp.Table):
            name = table.name
            if name and name not in tables:
                tables.append(name)
        return tables[:8]

    async def metadata_probe(self) -> OptimizeMetadata:
        tables = self.extract_tables()
        indexes: list[dict[str, Any]] = []
        statistics: list[dict[str, Any]] = []
        for table in tables[:3]:
            if hasattr(self.engine, "get_table_indexes"):
                rs = await self.engine.get_table_indexes(self.db_name or self.instance.db_name, table)
                if rs.is_success:
                    indexes.extend(_row_to_dict(rs.column_list, row) | {"table_name": table} for row in rs.rows[:20])
                elif rs.error:
                    statistics.append({"table_name": table, "kind": "metadata_warning", "message": rs.error})
        return OptimizeMetadata(tables=tables, indexes=indexes, statistics=statistics)

    def recommend(
        self,
        findings: list[OptimizeFinding],
        plan: OptimizePlan,
        metadata: OptimizeMetadata,
    ) -> list[OptimizeRecommendation]:
        recs: list[OptimizeRecommendation] = []
        codes = {item.code for item in findings}
        if {"FULL_SCAN", "TABLE_FULL_SCAN", "SEQ_SCAN"} & codes:
            recs.append(OptimizeRecommendation(
                priority=1,
                type="index",
                title="检查过滤字段索引",
                action="结合 WHERE/JOIN 条件评估高选择性联合索引或更新统计信息。",
                reason="执行计划显示存在全表扫描或大范围扫描。",
                risk="新增索引会增加写入和存储成本，上线前需评估业务写入压力。",
                confidence=0.82,
            ))
        if "SELECT_STAR" in codes:
            recs.append(OptimizeRecommendation(
                priority=2,
                type="rewrite",
                title="收窄返回列",
                action="只选择业务必需字段，避免 SELECT *。",
                reason="返回列过宽会放大网络传输、内存和脱敏成本。",
                confidence=0.9,
            ))
        if {"SORT", "FILESORT", "TEMPORARY", "ORDER_GROUP_COST"} & codes:
            recs.append(OptimizeRecommendation(
                priority=3,
                type="index",
                title="优化排序或聚合路径",
                action="检查 ORDER BY/GROUP BY 字段顺序与索引、分区或预聚合设计是否匹配。",
                reason="计划中存在排序、临时表或高代价聚合。",
                confidence=0.75,
            ))
        if {"HIGH_COST_JOIN", "HASH_JOIN", "NESTED_LOOP_HIGH_ROWS", "DATA_EXCHANGE"} & codes:
            recs.append(OptimizeRecommendation(
                priority=4,
                type="join",
                title="检查 Join 条件与数据分布",
                action="确认 Join 键索引、表大小估算、Join 顺序和分布式数据交换成本。",
                reason="计划中 Join 或数据移动可能是主要耗时来源。",
                confidence=0.7,
            ))
        if "NO_LIMIT" in codes:
            recs.append(OptimizeRecommendation(
                priority=5,
                type="rewrite",
                title="控制交互式查询结果集",
                action="为查询补充 LIMIT/TOP/FETCH 或分页条件。",
                reason="未限制结果集可能导致大结果返回。",
                confidence=0.7,
            ))
        if not recs:
            recs.append(OptimizeRecommendation(
                priority=9,
                type="general",
                title="结合执行计划继续确认",
                action="检查慢日志耗时、扫描/返回行数、索引选择性和业务访问模式。",
                reason="当前规则未命中明确高风险项。",
                confidence=0.55,
            ))
        return sorted(recs, key=lambda item: item.priority)


class JsonPlanAnalyzer(BaseSqlAnalyzer):
    plan_format = "json"

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        nodes = _walk_json_plan(raw)
        summary = self.empty_plan_summary()
        findings: list[OptimizeFinding] = []
        join_types: set[str] = set()
        for node in nodes:
            text = json.dumps(node, ensure_ascii=False).lower()
            node_type = str(node.get("Node Type") or node.get("access_type") or node.get("operator") or "")
            node_type_lower = node_type.lower()
            if node_type_lower in {"seq scan", "all"} or '"access_type": "all"' in text:
                summary["full_scan"] = True
            if "filesort" in text or node_type_lower == "sort":
                summary["sort"] = True
            if "temporary" in text:
                summary["temporary"] = True
            if "join" in node_type_lower:
                join_types.add(node_type.upper().replace(" ", "_"))
            summary["rows_estimate"] = max(
                int(summary["rows_estimate"]),
                _safe_int(node.get("Plan Rows") or node.get("rows_examined_per_scan") or node.get("rows_produced_per_join")),
            )
            summary["max_cost"] = max(
                int(summary["max_cost"]),
                _safe_int(node.get("Total Cost") or node.get("query_cost") or node.get("cost")),
            )
        summary["join_types"] = sorted(join_types)
        if summary["full_scan"]:
            findings.append(OptimizeFinding(
                severity="critical",
                code="FULL_SCAN",
                title="存在全表扫描",
                detail="执行计划显示存在 Seq Scan 或 access_type=ALL。",
                evidence="Seq Scan / access_type=ALL",
                confidence=0.9,
            ))
        if summary["sort"]:
            findings.append(OptimizeFinding(
                severity="warning",
                code="SORT",
                title="存在排序开销",
                detail="执行计划中出现排序或 filesort，可能需要优化 ORDER BY/GROUP BY 路径。",
                evidence="Sort / filesort",
                confidence=0.8,
            ))
        if summary["temporary"]:
            findings.append(OptimizeFinding(
                severity="warning",
                code="TEMPORARY",
                title="存在临时表开销",
                detail="执行计划中出现 temporary，中间结果集可能偏大。",
                evidence="temporary",
                confidence=0.75,
            ))
        return OptimizePlan(format="json", summary=summary, operators=nodes[:80]), findings


class MysqlAnalyzer(JsonPlanAnalyzer):
    engine_type = "mysql"
    support_level: SupportLevel = "full"

    async def explain(self) -> ResultSet:
        return await self.engine.explain_query(self.db_name, self.sql)

    def extract_raw(self, rs: ResultSet) -> Any:
        return _loads_json(_first_value(rs))


class PostgresAnalyzer(JsonPlanAnalyzer):
    engine_type = "pgsql"
    support_level: SupportLevel = "full"

    async def explain(self) -> ResultSet:
        return await self.engine.explain_query(self.db_name, self.sql)

    def extract_raw(self, rs: ResultSet) -> Any:
        return _loads_json(_first_value(rs))


class TidbAnalyzer(JsonPlanAnalyzer):
    engine_type = "tidb"
    support_level: SupportLevel = "full"

    async def explain(self) -> ResultSet:
        sql = f"EXPLAIN FORMAT='tidb_json' {self.sql.rstrip(';')}"
        rs = await self.engine.query(db_name=self.db_name, sql=sql, limit_num=1)
        if rs.is_success:
            return rs
        return await self.engine.query(db_name=self.db_name, sql=f"EXPLAIN {self.sql.rstrip(';')}", limit_num=100)

    def extract_raw(self, rs: ResultSet) -> Any:
        value = _first_value(rs)
        parsed = _loads_json(value)
        if not isinstance(parsed, str):
            return parsed
        return _result_raw(rs)

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        if isinstance(raw, (dict, list)):
            plan, findings = super().parse_plan(raw)
        else:
            plan, findings = TextPlanAnalyzer.parse_text_plan(raw, "tidb")
        text = json.dumps(raw, ensure_ascii=False).lower() if not isinstance(raw, str) else raw.lower()
        if "tablefullscan" in text or "table full scan" in text:
            findings.append(OptimizeFinding(
                severity="critical",
                code="TABLE_FULL_SCAN",
                title="TiDB 表全扫描",
                detail="TiDB 执行计划显示 TableFullScan，建议检查谓词、索引和统计信息。",
                evidence="TableFullScan",
                confidence=0.9,
            ))
            plan.summary["full_scan"] = True
        if "cop[tikv]" in text or "cop[tiflash]" in text:
            plan.summary["tasks"] = sorted(set(re.findall(r"cop\[[^\]]+\]|root", text)))
        return plan, findings


class TextPlanAnalyzer(BaseSqlAnalyzer):
    plan_format = "text"

    @staticmethod
    def parse_text_plan(raw: Any, engine_type: str) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        if isinstance(raw, dict):
            rows = raw.get("rows", [])
            text = "\n".join(" ".join(str(v) for v in row) if isinstance(row, (list, tuple)) else str(row) for row in rows)
        else:
            text = str(raw or "")
        lower = text.lower()
        summary = {
            "full_scan": any(token in lower for token in ["table scan", "table access full", "seq scan", "tablefullscan"]),
            "rows_estimate": _max_number_after(text, ["rows", "cardinality", "row"]),
            "max_cost": _max_number_after(text, ["cost"]),
            "join_types": sorted({name for name in ["HASH_JOIN", "NESTED_LOOP", "MERGE_JOIN", "BROADCAST", "SHUFFLE", "COLOCATE"] if name.lower().replace("_", " ") in lower or name.lower() in lower}),
            "sort": "sort" in lower or "top-n" in lower or "topn" in lower,
            "temporary": "temporary" in lower or "tempdb" in lower,
        }
        findings: list[OptimizeFinding] = []
        if summary["full_scan"]:
            findings.append(OptimizeFinding(
                severity="critical",
                code="FULL_SCAN",
                title=f"{_db_type_label(engine_type)} 计划存在全表扫描",
                detail="计划文本命中全表扫描特征，建议检查过滤条件、索引或统计信息。",
                evidence="table scan / TABLE ACCESS FULL / TableFullScan",
                confidence=0.78,
            ))
        if summary["sort"]:
            findings.append(OptimizeFinding(
                severity="warning",
                code="ORDER_GROUP_COST",
                title="排序或聚合可能成本较高",
                detail="计划文本命中 Sort、TOP-N 或相关聚合算子。",
                evidence="SORT / TOP-N",
                confidence=0.7,
            ))
        if "exchange" in lower:
            findings.append(OptimizeFinding(
                severity="warning",
                code="DATA_EXCHANGE",
                title="存在分布式数据交换",
                detail="计划出现 EXCHANGE，可能存在跨节点数据移动成本。",
                evidence="EXCHANGE",
                confidence=0.72,
            ))
        return OptimizePlan(format="text", summary=summary, operators=[]), findings

    def extract_raw(self, rs: ResultSet) -> Any:
        return _result_raw(rs)

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        return self.parse_text_plan(raw, self.engine_type)


class StarRocksAnalyzer(TextPlanAnalyzer):
    engine_type = "starrocks"
    support_level: SupportLevel = "full"

    async def explain(self) -> ResultSet:
        return await self.engine.query(db_name=self.db_name, sql=f"EXPLAIN COSTS {self.sql.rstrip(';')}", limit_num=1000)

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        plan, findings = self.parse_text_plan(raw, "starrocks")
        text = json.dumps(raw, ensure_ascii=False).lower()
        if "olapscan" in text or "scan [" in text:
            plan.summary["scan_operator"] = True
        if "predicate" not in text and ("olapscan" in text or "scan [" in text):
            findings.append(OptimizeFinding(
                severity="warning",
                code="PREDICATE_PUSHDOWN",
                title="未看到明确谓词下推",
                detail="StarRocks 计划中未识别到 predicate/PushdownPredicates，建议确认过滤条件是否下推。",
                evidence="predicate",
                confidence=0.6,
            ))
        if "broadcast" in text or "shuffle" in text or "colocate" in text:
            findings.append(OptimizeFinding(
                severity="info",
                code="STARROCKS_JOIN_DISTRIBUTION",
                title="检查 StarRocks Join 分布策略",
                detail="计划包含 BROADCAST/SHUFFLE/COLOCATE 等分布策略，需结合表大小和分桶方式判断。",
                evidence="BROADCAST / SHUFFLE / COLOCATE",
                confidence=0.68,
            ))
        return plan, findings


class OracleAnalyzer(TextPlanAnalyzer):
    engine_type = "oracle"
    support_level: SupportLevel = "full"

    async def explain(self) -> ResultSet:
        if hasattr(self.engine, "explain_query"):
            return await self.engine.explain_query(self.db_name, self.sql)
        return ResultSet(warning="Oracle 引擎未实现 DBMS_XPLAN")


class MssqlAnalyzer(TextPlanAnalyzer):
    engine_type = "mssql"
    support_level: SupportLevel = "full"
    plan_format = "xml"

    async def explain(self) -> ResultSet:
        if hasattr(self.engine, "explain_query"):
            return await self.engine.explain_query(self.db_name, self.sql)
        return ResultSet(warning="MSSQL 引擎未实现 SHOWPLAN_XML")

    def parse_plan(self, raw: Any) -> tuple[OptimizePlan, list[OptimizeFinding]]:
        plan, findings = self.parse_text_plan(raw, "mssql")
        plan.format = "xml"
        text = json.dumps(raw, ensure_ascii=False).lower()
        if "missingindex" in text:
            findings.append(OptimizeFinding(
                severity="warning",
                code="MISSING_INDEX",
                title="SQL Server 计划提示缺失索引",
                detail="ShowPlan XML 中包含 MissingIndex 信息，请结合写入成本评估索引候选。",
                evidence="MissingIndex",
                confidence=0.82,
            ))
        if "key lookup" in text:
            findings.append(OptimizeFinding(
                severity="warning",
                code="KEY_LOOKUP",
                title="存在 Key Lookup",
                detail="频繁 Key Lookup 可能说明非聚集索引未覆盖查询列。",
                evidence="Key Lookup",
                confidence=0.78,
            ))
        return plan, findings


class PartialExplainAnalyzer(TextPlanAnalyzer):
    support_level: SupportLevel = "partial"

    async def explain(self) -> ResultSet:
        return await self.engine.query(db_name=self.db_name, sql=f"EXPLAIN {self.sql.rstrip(';')}", limit_num=300)


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _max_number_after(text: str, keys: list[str]) -> int:
    values: list[int] = []
    for key in keys:
        for match in re.finditer(rf"{re.escape(key)}\D{{0,20}}([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE):
            values.append(_safe_int(match.group(1)))
    return max(values) if values else 0


def _analyzer_for(instance: Instance, engine: Any, db_name: str, sql: str) -> BaseSqlAnalyzer:
    db_type = instance.db_type.lower()
    mapping: dict[str, type[BaseSqlAnalyzer]] = {
        "mysql": MysqlAnalyzer,
        "pgsql": PostgresAnalyzer,
        "postgres": PostgresAnalyzer,
        "postgresql": PostgresAnalyzer,
        "tidb": TidbAnalyzer,
        "starrocks": StarRocksAnalyzer,
        "oracle": OracleAnalyzer,
        "mssql": MssqlAnalyzer,
        "sqlserver": MssqlAnalyzer,
        "clickhouse": PartialExplainAnalyzer,
        "doris": PartialExplainAnalyzer,
    }
    analyzer_cls = mapping.get(db_type, BaseSqlAnalyzer)
    analyzer = analyzer_cls(instance, engine, db_name, sql)
    analyzer.engine_type = db_type
    if db_type in _PARTIAL_ENGINES:
        analyzer.support_level = "partial"
    return analyzer


class OptimizeService:
    """Unified SQL optimization v2 entrypoint."""

    @staticmethod
    async def analyze(db: AsyncSession, user: dict, data: OptimizeAnalyzeRequest) -> OptimizeAnalyzeResponse:
        instance, source, db_name, sql, slowlog_meta = await OptimizeService._resolve_input(db, user, data)
        db_type = instance.db_type.lower()
        if db_type in _UNSUPPORTED_ENGINES:
            static = BaseSqlAnalyzer(instance, None, db_name, sql).static_analyze()
            return OptimizeAnalyzeResponse(
                supported=False,
                support_level="unsupported",
                engine=db_type,
                source=source,
                risk_score=OptimizeService._risk_score(static, slowlog_meta),
                summary=f"{_db_type_label(instance.db_type)} 不进入 SQL 优化主链路，仅保留请求信息。",
                findings=static,
                recommendations=[],
                metadata=OptimizeMetadata(tables=[], slowlog=slowlog_meta),
                raw=None,
                sql=sql,
                msg=f"{_db_type_label(instance.db_type)} 暂不适用 SQL 优化诊断",
            )

        engine = get_engine(instance)
        analyzer = _analyzer_for(instance, engine, db_name, sql)
        result = await analyzer.analyze()
        result.metadata.slowlog = slowlog_meta
        risk_score = OptimizeService._risk_score(result.findings, slowlog_meta)
        return OptimizeAnalyzeResponse(
            supported=result.support_level != "unsupported",
            support_level=result.support_level,
            engine=db_type,
            source=source,
            risk_score=risk_score,
            summary=OptimizeService._summary(db_type, risk_score, result.findings, result.msg),
            findings=result.findings,
            recommendations=result.recommendations,
            plan=result.plan,
            metadata=result.metadata,
            raw=result.raw,
            sql=sql,
            msg=result.msg,
        )

    @staticmethod
    async def _resolve_input(
        db: AsyncSession,
        user: dict,
        data: OptimizeAnalyzeRequest,
    ) -> tuple[Instance, OptimizeSource, str, str, dict[str, Any]]:
        if data.log_id:
            result = await db.execute(select(SlowQueryLog).where(SlowQueryLog.id == data.log_id))
            log = result.scalar_one_or_none()
            if not log:
                raise NotFoundException("慢 SQL 记录不存在")
            if not log.instance_id:
                raise AppException("慢 SQL 记录缺少实例信息", code=422)
            instance = await SlowLogService.get_instance_or_404(db, log.instance_id, user)
            return instance, "slowlog", log.db_name or instance.db_name, log.sql_text, OptimizeService._slowlog_meta(log)

        if data.fingerprint:
            instance_ids = await SlowLogService.scoped_instance_ids(db, user)
            stmt = select(SlowQueryLog).where(SlowQueryLog.sql_fingerprint == data.fingerprint)
            if data.instance_id:
                stmt = stmt.where(SlowQueryLog.instance_id == data.instance_id)
            if instance_ids is not None:
                stmt = stmt.where(SlowQueryLog.instance_id.in_(instance_ids or [-1]))
            result = await db.execute(stmt.order_by(SlowQueryLog.duration_ms.desc(), SlowQueryLog.occurred_at.desc()).limit(1))
            log = result.scalar_one_or_none()
            if not log or not log.instance_id:
                raise NotFoundException("慢 SQL 指纹不存在或无权访问")
            instance = await SlowLogService.get_instance_or_404(db, log.instance_id, user)
            return instance, "fingerprint", log.db_name or instance.db_name, log.sql_text, OptimizeService._slowlog_meta(log)

        if not data.instance_id:
            raise AppException("缺少 instance_id", code=422)
        instance = await SlowLogService.get_instance_or_404(db, data.instance_id, user)
        return instance, "manual", data.db_name or instance.db_name, data.sql, {}

    @staticmethod
    def _slowlog_meta(log: SlowQueryLog) -> dict[str, Any]:
        return {
            "log_id": log.id,
            "source": log.source,
            "duration_ms": log.duration_ms,
            "rows_examined": log.rows_examined,
            "rows_sent": log.rows_sent,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "analysis_tags": log.analysis_tags or [],
        }

    @staticmethod
    def _risk_score(findings: list[OptimizeFinding], slowlog: dict[str, Any]) -> int:
        score = sum(_severity_score(item.severity) for item in findings if item.code != "STATIC_PASS")
        codes = {item.code for item in findings}
        if {"FULL_SCAN", "TABLE_FULL_SCAN", "SEQ_SCAN"} & codes:
            score += 24
        if slowlog.get("duration_ms", 0) >= 10000:
            score += 18
        if slowlog.get("rows_examined", 0) >= 100000:
            score += 18
        if slowlog.get("rows_sent", 0) >= 10000:
            score += 10
        return max(0, min(score, 100))

    @staticmethod
    def _summary(db_type: str, risk_score: int, findings: list[OptimizeFinding], msg: str = "") -> str:
        if msg and risk_score == 0:
            return msg
        critical = [item.title for item in findings if item.severity == "critical"]
        warning = [item.title for item in findings if item.severity == "warning"]
        if risk_score >= 70:
            return f"{_db_type_label(db_type)} SQL 风险较高，建议优先处理：{'、'.join((critical or warning)[:3])}。"
        if risk_score >= 35:
            return f"{_db_type_label(db_type)} SQL 存在可优化项：{'、'.join((warning or critical)[:3])}。"
        return f"{_db_type_label(db_type)} SQL 未发现明确高风险项，建议结合业务峰值和索引选择性继续确认。"
