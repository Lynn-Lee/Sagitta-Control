"""
慢日志分析路由（Sprint 4）。
使用 PostgreSQL 的 pg_stat_statements 或引擎自带慢查询日志。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as QParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user
from app.engines.registry import get_engine
from app.models.instance import Instance

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="慢查询列表")
async def list_slow_queries(
    instance_id: int = QParam(...),
    db_name: str | None = None,
    limit: int = QParam(50, ge=1, le=500),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.is_active)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "实例不存在")

    engine = get_engine(inst)

    if inst.db_type == "pgsql":
        # PostgreSQL: 使用 pg_stat_activity 查当前慢查询
        sql = """
            SELECT pid, usename, datname, state,
                   extract(epoch from (now()-query_start))::int AS duration_seconds,
                   query
            FROM pg_stat_activity
            WHERE state != 'idle'
              AND query_start < now() - interval '1 second'
              AND pid != pg_backend_pid()
            ORDER BY duration_seconds DESC
            LIMIT $1
        """
        rs = await engine._raw_query(db_name=inst.db_name, sql=sql, args=[limit])
    elif inst.db_type == "mysql":
        sql = f"""
            SELECT Id, User, Host, db, Command, Time, State, LEFT(Info,200) AS Info
            FROM information_schema.PROCESSLIST
            WHERE Command != 'Sleep' AND Time > 1
            ORDER BY Time DESC
            LIMIT {limit}
        """
        rs = await engine.query(db_name="information_schema", sql=sql, limit_num=limit)
    elif inst.db_type == "starrocks":
        rs = await engine.processlist(command_type="ALL")
        if rs.is_success:
            def _time_value(row: object) -> int:
                if isinstance(row, dict):
                    value = row.get("Time", row.get("TIME", 0))
                    try:
                        return int(value or 0)
                    except Exception:
                        return 0
                return 0

            rs.rows = [
                row for row in rs.rows
                if (
                    not isinstance(row, dict)
                    or str(row.get("Command", row.get("COMMAND", ""))).lower() != "sleep"
                )
                and _time_value(row) > 1
            ][:limit]
    else:
        return {"items": [], "msg": f"{inst.db_type} 暂不支持慢查询分析"}

    if rs.error:
        raise HTTPException(400, f"查询慢日志失败：{rs.error}")

    cols = rs.column_list or []
    return {
        "items": [dict(zip(cols, r, strict=False)) if isinstance(r, tuple) else r for r in rs.rows],
        "total": len(rs.rows),
    }


@router.get("/stats/", summary="慢查询统计（PostgreSQL pg_stat_statements）")
async def slow_query_stats(
    instance_id: int = QParam(...),
    limit: int = QParam(20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.is_active)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "实例不存在")

    if inst.db_type != "pgsql":
        return {"items": [], "msg": "仅 PostgreSQL 支持 pg_stat_statements"}

    engine = get_engine(inst)
    sql = """
        SELECT query, calls, round(total_exec_time::numeric, 2) AS total_ms,
               round(mean_exec_time::numeric, 2) AS avg_ms,
               round(stddev_exec_time::numeric, 2) AS stddev_ms,
               rows
        FROM pg_stat_statements
        ORDER BY mean_exec_time DESC
        LIMIT $1
    """
    try:
        rs = await engine._raw_query(db_name=inst.db_name, sql=sql, args=[limit])
        if rs.error:
            return {"items": [], "msg": "pg_stat_statements 扩展未安装"}
        cols = rs.column_list or []
        return {"items": [dict(zip(cols, r, strict=False)) for r in rs.rows]}
    except Exception as e:
        return {"items": [], "msg": f"pg_stat_statements 不可用：{str(e)}"}
