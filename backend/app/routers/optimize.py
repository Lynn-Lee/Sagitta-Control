"""
SQL 优化路由（Sprint 4）。
提供 EXPLAIN 分析和 sqlglot 语法建议。
"""
import logging

import sqlglot
import sqlglot.expressions as exp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user
from app.engines.registry import get_engine
from app.models.instance import Instance
from app.schemas.optimize import OptimizeAnalyzeRequest, OptimizeAnalyzeResponse
from app.services.optimize import OptimizeService

logger = logging.getLogger(__name__)
router = APIRouter()


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
}


def _db_type_label(db_type: str) -> str:
    return _DB_TYPE_LABELS.get(db_type.lower(), db_type)


class OptimizeRequest(BaseModel):
    instance_id: int
    db_name: str
    sql: str


@router.post("/analyze/", response_model=OptimizeAnalyzeResponse, summary="SQL 优化 v2 统一诊断")
async def analyze_sql(
    data: OptimizeAnalyzeRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OptimizeService.analyze(db, user, data)


@router.post("/explain/", summary="EXPLAIN 执行计划")
async def explain_sql(
    data: OptimizeRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Instance).where(Instance.id == data.instance_id, Instance.is_active)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "实例不存在")

    engine = get_engine(inst)

    if inst.db_type == "pgsql":
        explain_sql = f"EXPLAIN (FORMAT JSON, ANALYZE false, BUFFERS false) {data.sql.rstrip(';')}"
        rs = await engine.query(db_name=data.db_name, sql=explain_sql, limit_num=0)
    elif inst.db_type in {"mysql", "starrocks"}:
        explain_sql = f"EXPLAIN {data.sql.rstrip(';')}"
        rs = await engine.query(db_name=data.db_name, sql=explain_sql, limit_num=100)
    else:
        return {"error": f"{_db_type_label(inst.db_type)} 暂不支持 EXPLAIN"}

    if rs.error:
        raise HTTPException(400, f"EXPLAIN 失败：{rs.error}")

    cols = rs.column_list or []
    return {
        "column_list": cols,
        "rows": [list(r) if isinstance(r, tuple) else r for r in rs.rows],
        "db_type": inst.db_type,
    }


@router.post("/advice/", summary="SQL 优化建议（sqlglot 规则引擎）")
async def sql_advice(
    data: OptimizeRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    使用 sqlglot 对 SQL 进行静态分析，给出优化建议。
    """
    result = await db.execute(
        select(Instance).where(Instance.id == data.instance_id)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "实例不存在")

    dialect_map = {
        "mysql": "mysql", "starrocks": "mysql", "pgsql": "postgres", "oracle": "oracle",
        "clickhouse": "clickhouse", "mssql": "tsql",
    }
    dialect = dialect_map.get(inst.db_type, "mysql")
    advices = []

    try:
        tree = sqlglot.parse_one(data.sql, dialect=dialect)

        # 规则1：SELECT * 警告
        if tree.find(exp.Star):
            advices.append({
                "level": "warning",
                "rule": "SELECT_STAR",
                "message": "避免使用 SELECT *，建议明确指定需要的列，减少网络传输和内存占用",
            })

        # 规则2：UPDATE/DELETE 无 WHERE 条件
        if isinstance(tree, (exp.Update, exp.Delete)) and not tree.find(exp.Where):
            advices.append({
                "level": "error",
                "rule": "NO_WHERE",
                "message": "UPDATE/DELETE 语句缺少 WHERE 条件，可能导致全表更新/删除",
            })

        # 规则3：LIKE 前导通配符
        for like in tree.find_all(exp.Like):
            pattern = str(like.right)
            if pattern.startswith("'%") or pattern.startswith("'_"):
                advices.append({
                    "level": "warning",
                    "rule": "LIKE_LEADING_WILDCARD",
                    "message": f"LIKE '{pattern}' 使用了前导通配符，无法使用索引，建议考虑全文索引",
                })

        # 规则4：子查询建议
        subquery_count = len(list(tree.find_all(exp.Subquery)))
        if subquery_count > 2:
            advices.append({
                "level": "info",
                "rule": "DEEP_SUBQUERY",
                "message": f"SQL 包含 {subquery_count} 层子查询，建议考虑用 JOIN 或 CTE 替代以提升可读性和性能",
            })

        # 规则5：无 LIMIT 的 SELECT
        if isinstance(tree, exp.Select) and not tree.find(exp.Limit):
            advices.append({
                "level": "info",
                "rule": "NO_LIMIT",
                "message": "SELECT 语句没有 LIMIT 子句，大表查询可能返回大量数据",
            })

        if not advices:
            advices.append({
                "level": "ok",
                "rule": "PASS",
                "message": "SQL 通过基础规则检查，未发现明显问题",
            })

    except sqlglot.errors.ParseError as e:
        advices.append({
            "level": "error",
            "rule": "PARSE_ERROR",
            "message": f"SQL 解析失败：{str(e)}",
        })

    return {"advices": advices, "sql": data.sql}
