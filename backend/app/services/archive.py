"""
数据归档服务（Pack E 重写）。

设计原则：
1. 通过引擎层适配所有数据库，不支持的直接返回明确提示
2. purge 模式：分批删除（各数据库语法不同，统一抽象）
3. dest 模式：跨实例迁移（INSERT + DELETE）
4. dry_run：先估算，再执行，防止误操作

各数据库支持情况：
  MySQL/TiDB/Doris  purge + dest  DELETE ... LIMIT N
  PostgreSQL        purge + dest  DELETE WHERE ctid IN (LIMIT N)
  Oracle            purge + dest  DELETE WHERE ROWNUM <= N
  MSSQL             purge + dest  DELETE TOP(N) FROM ...
  StarRocks         purge only    DELETE FROM ... WHERE ...
  ClickHouse        purge only    ALTER TABLE ... DELETE WHERE (异步)
  MongoDB           purge + dest  deleteMany with limit
  Cassandra         purge only    DELETE + IF EXISTS（无 LIMIT，需用 SELECT+批量DELETE）
  Redis             不支持        直接返回提示
  Elasticsearch     不支持        直接返回提示
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.engines.registry import get_engine
from app.models.instance import Instance

logger = logging.getLogger(__name__)

# ── 各数据库支持配置 ──────────────────────────────────────────
ARCHIVE_SUPPORT: dict[str, dict] = {
    "mysql":         {"purge": True,  "dest": True,  "batch_delete": "limit"},
    "tidb":          {"purge": True,  "dest": True,  "batch_delete": "limit"},
    "doris":         {"purge": True,  "dest": False, "batch_delete": "limit"},
    "pgsql":         {"purge": True,  "dest": True,  "batch_delete": "ctid"},
    "oracle":        {"purge": True,  "dest": True,  "batch_delete": "rownum"},
    "mssql":         {"purge": True,  "dest": True,  "batch_delete": "top"},
    "starrocks":     {"purge": True,  "dest": False, "batch_delete": "where"},
    "clickhouse":    {"purge": True,  "dest": False, "batch_delete": "ch_alter"},
    "mongo":         {"purge": True,  "dest": True,  "batch_delete": "mongo"},
    "cassandra":     {"purge": True,  "dest": False, "batch_delete": "cassandra"},
    "redis":         {"purge": False, "dest": False, "reason": "Redis 为键值存储，不支持条件归档"},
    "elasticsearch": {"purge": False, "dest": False, "reason": "Elasticsearch 请使用 ILM 生命周期管理"},
    "opensearch":    {"purge": False, "dest": False, "reason": "OpenSearch 请使用 ISM 策略管理"},
}


def check_support(db_type: str, mode: str) -> tuple[bool, str]:
    """检查数据库类型是否支持指定归档模式。"""
    cfg = ARCHIVE_SUPPORT.get(db_type.lower())
    if not cfg:
        return False, f"数据库类型 {db_type} 未在支持列表中，暂不支持数据归档"
    if not cfg.get(mode):
        reason = cfg.get("reason", f"{db_type} 不支持 {mode} 归档模式")
        return False, reason
    return True, ""


def build_batch_delete_sql(db_type: str, table_name: str, condition: str, batch_size: int) -> str:
    """根据数据库类型构建分批删除 SQL。"""
    dt = db_type.lower()
    t = table_name

    if dt in ("mysql", "tidb", "doris"):
        return f"DELETE FROM `{t}` WHERE {condition} LIMIT {batch_size}"

    elif dt == "pgsql":
        return (f'DELETE FROM "{t}" WHERE ctid IN '
                f'(SELECT ctid FROM "{t}" WHERE {condition} LIMIT {batch_size})')

    elif dt == "oracle":
        return (f'DELETE FROM "{t}" WHERE ROWID IN '
                f'(SELECT ROWID FROM "{t}" WHERE {condition} AND ROWNUM <= {batch_size})')

    elif dt == "mssql":
        return f"DELETE TOP({batch_size}) FROM [{t}] WHERE {condition}"

    elif dt == "starrocks":
        return f"DELETE FROM `{t}` WHERE {condition}"

    elif dt == "clickhouse":
        # ClickHouse ALTER TABLE DELETE 是异步的，无法精确分批
        return f"ALTER TABLE {t} DELETE WHERE {condition}"

    elif dt == "cassandra":
        # Cassandra 无 LIMIT DELETE，返回标记让调用方特殊处理
        return f"__CASSANDRA_DELETE__{t}|{condition}|{batch_size}"

    return f"DELETE FROM {t} WHERE {condition} LIMIT {batch_size}"


def build_count_sql(db_type: str, table_name: str, condition: str) -> str:
    """构建 COUNT 估算 SQL。"""
    dt = db_type.lower()
    t = table_name

    if dt in ("mysql", "tidb", "doris", "starrocks"):
        return f"SELECT COUNT(*) FROM `{t}` WHERE {condition}"
    elif dt in ("pgsql", "oracle", "mssql"):
        return f'SELECT COUNT(*) FROM "{t}" WHERE {condition}'
    elif dt == "clickhouse":
        return f"SELECT count() FROM {t} WHERE {condition}"
    else:
        return f"SELECT COUNT(*) FROM {t} WHERE {condition}"


class ArchiveService:
    @staticmethod
    def _first_value(row: Any) -> Any:
        if isinstance(row, dict):
            return next(iter(row.values()), 0)
        if isinstance(row, (tuple, list)):
            return row[0] if row else 0
        return row

    @staticmethod
    async def _load_instance(db: AsyncSession, instance_id: int) -> Instance:
        result = await db.execute(select(Instance).where(Instance.id == instance_id))
        inst = result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        return inst

    # ── 估算影响行数 ──────────────────────────────────────────

    @staticmethod
    async def estimate_rows(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        table_name: str,
        condition: str,
    ) -> dict:
        inst = await ArchiveService._load_instance(db, instance_id)
        supported, reason = check_support(inst.db_type, "purge")
        if not supported:
            return {"count": -1, "supported": False, "msg": reason}

        engine = get_engine(inst)

        # MongoDB 特殊处理
        if inst.db_type == "mongo":
            try:
                client = await engine.get_connection(db_name)
                col = client[db_name][table_name]
                import json
                try:
                    filter_dict = json.loads(condition)
                except Exception:
                    filter_dict = {}
                count = await col.count_documents(filter_dict)
                return {"count": count, "supported": True, "msg": f"符合条件：{count} 条文档",
                        "table": table_name, "condition": condition}
            except Exception as e:
                return {"count": -1, "supported": True, "msg": f"估算失败：{str(e)}"}

        count_sql = build_count_sql(inst.db_type, table_name, condition)
        rs = await engine.query(db_name=db_name, sql=count_sql, limit_num=1)
        if rs.error:
            return {"count": -1, "supported": True, "msg": f"估算失败：{rs.error}"}

        count = ArchiveService._first_value(rs.rows[0]) if rs.rows else 0
        return {
            "count": count,
            "supported": True,
            "msg": f"符合条件的数据：{count} 行",
            "table": table_name,
            "condition": condition,
            "db_type": inst.db_type,
        }

    # ── purge 模式（分批删除）────────────────────────────────

    @staticmethod
    async def run_purge(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        table_name: str,
        condition: str,
        batch_size: int = 1000,
        sleep_ms: int = 100,
        dry_run: bool = False,
    ) -> dict:
        inst = await ArchiveService._load_instance(db, instance_id)
        supported, reason = check_support(inst.db_type, "purge")
        if not supported:
            return {"success": False, "supported": False, "msg": reason}

        # 先估算
        estimate = await ArchiveService.estimate_rows(db, instance_id, db_name, table_name, condition)
        if dry_run:
            return {**estimate, "dry_run": True, "mode": "purge"}

        if estimate["count"] < 0:
            return {"success": False, "supported": True, "msg": estimate.get("msg", "归档估算失败")}

        if estimate["count"] == 0:
            return {"success": True, "total_deleted": 0, "msg": "没有符合条件的数据，无需归档"}

        engine = get_engine(inst)

        # MongoDB 单独处理
        if inst.db_type == "mongo":
            return await ArchiveService._purge_mongo(
                engine, db_name, table_name, condition, batch_size, sleep_ms
            )

        # ClickHouse：ALTER TABLE DELETE（异步，不分批）
        if inst.db_type == "clickhouse":
            delete_sql = f"ALTER TABLE {table_name} DELETE WHERE {condition}"
            rs = await engine.execute(db_name=db_name, sql=delete_sql)
            if rs.error:
                return {"success": False, "msg": f"ClickHouse 归档失败：{rs.error}"}
            return {
                "success": True, "mode": "purge",
                "msg": "ClickHouse DELETE 已提交（异步执行，请通过 system.mutations 查看进度）",
                "total_deleted": estimate["count"],
            }

        # StarRocks：DELETE 必须带 WHERE，不使用 MySQL DELETE ... LIMIT 分批模型。
        if inst.db_type == "starrocks":
            delete_sql = build_batch_delete_sql(inst.db_type, table_name, condition, batch_size)
            rs = await engine.execute(db_name=db_name, sql=delete_sql)
            if rs.error:
                return {"success": False, "msg": f"StarRocks 归档失败：{rs.error}"}
            return {
                "success": True,
                "mode": "purge",
                "total_deleted": estimate["count"],
                "msg": f"StarRocks 归档完成，共删除约 {estimate['count']} 行",
            }

        # Cassandra：SELECT + 批量 DELETE
        if inst.db_type == "cassandra":
            return await ArchiveService._purge_cassandra(
                engine, db_name, table_name, condition, batch_size, sleep_ms
            )

        # 通用分批 DELETE（MySQL/PgSQL/Oracle/MSSQL/TiDB/Doris）
        delete_sql = build_batch_delete_sql(inst.db_type, table_name, condition, batch_size)
        count_sql = build_count_sql(inst.db_type, table_name, condition)
        total_deleted = 0

        for batch in range(10000):
            rs = await engine.execute(db_name=db_name, sql=delete_sql)
            if rs.error:
                return {
                    "success": False,
                    "total_deleted": total_deleted,
                    "msg": f"第 {batch+1} 批执行失败：{rs.error}",
                }
            total_deleted += batch_size

            # 检查剩余行数
            count_rs = await engine.query(db_name=db_name, sql=count_sql, limit_num=1)
            remaining = ArchiveService._first_value(count_rs.rows[0]) if count_rs.rows else 0
            logger.info("archive_purge: batch=%d total_deleted=%d remaining=%d",
                        batch+1, total_deleted, remaining)

            if remaining == 0:
                break
            if sleep_ms > 0:
                await asyncio.sleep(sleep_ms / 1000)

        return {
            "success": True, "mode": "purge",
            "total_deleted": total_deleted,
            "msg": f"归档完成，共删除约 {total_deleted} 行",
        }

    @staticmethod
    async def _purge_mongo(engine: Any, db_name: str, collection: str,
                           condition: str, batch_size: int, sleep_ms: int) -> dict:
        """MongoDB 分批删除。"""
        import json
        try:
            filter_dict = json.loads(condition)
        except Exception:
            return {"success": False, "msg": "MongoDB 归档条件必须是合法的 JSON 格式，如 {\"created_at\": {\"$lt\": ...}}"}

        total_deleted = 0
        try:
            client = await engine.get_connection(db_name)
            col = client[db_name][collection]
            for _ in range(10000):
                # 分批：先查出 _id 列表，再删除
                cursor = col.find(filter_dict, {"_id": 1}).limit(batch_size)
                ids = [doc["_id"] async for doc in cursor]
                if not ids:
                    break
                result = await col.delete_many({"_id": {"$in": ids}})
                total_deleted += result.deleted_count
                if result.deleted_count < batch_size:
                    break
                if sleep_ms > 0:
                    await asyncio.sleep(sleep_ms / 1000)
        except Exception as e:
            return {"success": False, "total_deleted": total_deleted, "msg": str(e)}

        return {"success": True, "mode": "purge", "total_deleted": total_deleted,
                "msg": f"MongoDB 归档完成，共删除 {total_deleted} 条文档"}

    @staticmethod
    async def _purge_cassandra(engine: Any, db_name: str, table: str,
                                condition: str, batch_size: int, sleep_ms: int) -> dict:
        """Cassandra 通过 SELECT + DELETE 分批归档。"""
        total_deleted = 0
        try:
            for _ in range(10000):
                # 查出一批主键
                select_rs = await engine.query(
                    db_name=db_name,
                    sql=f"SELECT * FROM {table} WHERE {condition} LIMIT {batch_size}",
                    limit_num=batch_size,
                )
                if not select_rs.rows:
                    break
                # 逐行删除（Cassandra 需要主键删除）
                pk_cols = select_rs.column_list[:1]  # 取第一列作为主键（简化处理）
                for row in select_rs.rows:
                    pk_val = row[0]
                    del_sql = f"DELETE FROM {table} WHERE {pk_cols[0]} = '{pk_val}'"
                    await engine.execute(db_name=db_name, sql=del_sql)
                total_deleted += len(select_rs.rows)
                if len(select_rs.rows) < batch_size:
                    break
                if sleep_ms > 0:
                    await asyncio.sleep(sleep_ms / 1000)
        except Exception as e:
            return {"success": False, "total_deleted": total_deleted, "msg": str(e)}

        return {"success": True, "mode": "purge", "total_deleted": total_deleted,
                "msg": f"Cassandra 归档完成，共删除 {total_deleted} 行"}

    # ── dest 模式（INSERT 到目标 + DELETE 源）────────────────

    @staticmethod
    async def run_to_dest(
        db: AsyncSession,
        src_instance_id: int, src_db: str, src_table: str, condition: str,
        dest_instance_id: int, dest_db: str, dest_table: str,
        batch_size: int = 1000, sleep_ms: int = 100,
        dry_run: bool = False,
    ) -> dict:
        src_inst = await ArchiveService._load_instance(db, src_instance_id)
        supported, reason = check_support(src_inst.db_type, "dest")
        if not supported:
            return {"success": False, "supported": False, "msg": reason}

        # dry_run 只估算
        if dry_run:
            return await ArchiveService.estimate_rows(
                db, src_instance_id, src_db, src_table, condition
            ) | {"dry_run": True, "mode": "dest"}

        dest_inst = await ArchiveService._load_instance(db, dest_instance_id)
        src_engine = get_engine(src_inst)
        dest_engine = get_engine(dest_inst)

        # MongoDB 单独处理
        if src_inst.db_type == "mongo":
            return await ArchiveService._dest_mongo(
                src_engine, dest_engine, src_db, src_table, condition,
                dest_db, dest_table, batch_size, sleep_ms,
            )

        # 通用 SELECT + INSERT + DELETE
        dt = src_inst.db_type
        if dt in ("mysql", "tidb", "doris"):
            select_sql = f"SELECT * FROM `{src_table}` WHERE {condition} LIMIT {batch_size}"
            delete_sql = f"DELETE FROM `{src_table}` WHERE {condition} LIMIT {batch_size}"
        elif dt == "pgsql":
            select_sql = f'SELECT * FROM "{src_table}" WHERE {condition} LIMIT {batch_size}'
            delete_sql = (f'DELETE FROM "{src_table}" WHERE ctid IN '
                          f'(SELECT ctid FROM "{src_table}" WHERE {condition} LIMIT {batch_size})')
        elif dt == "oracle":
            select_sql = f'SELECT * FROM "{src_table}" WHERE {condition} AND ROWNUM <= {batch_size}'
            delete_sql = (f'DELETE FROM "{src_table}" WHERE ROWID IN '
                          f'(SELECT ROWID FROM "{src_table}" WHERE {condition} AND ROWNUM <= {batch_size})')
        elif dt == "mssql":
            select_sql = f"SELECT TOP {batch_size} * FROM [{src_table}] WHERE {condition}"
            delete_sql = f"DELETE TOP({batch_size}) FROM [{src_table}] WHERE {condition}"
        else:
            return {"success": False, "msg": f"{dt} 的 dest 模式暂不支持"}

        total_moved = 0
        for batch in range(10000):
            rs = await src_engine.query(db_name=src_db, sql=select_sql, limit_num=batch_size)
            if rs.error or not rs.rows:
                break

            # 构建 INSERT
            cols = ArchiveService._quote_cols(rs.column_list, dt)
            rows_values = []
            for row in rs.rows:
                parts = []
                for v in row:
                    if v is None:
                        parts.append("NULL")
                    else:
                        safe = str(v).replace("'", "''")
                        parts.append(f"'{safe}'")
                rows_values.append("(" + ", ".join(parts) + ")")

            tbl_dest = f'"{dest_table}"' if dt in ("pgsql", "oracle") else f"`{dest_table}`"
            insert_sql = f"INSERT INTO {tbl_dest} ({cols}) VALUES " + ", ".join(rows_values)

            insert_rs = await dest_engine.execute(db_name=dest_db, sql=insert_sql)
            if insert_rs.error:
                return {"success": False, "total_moved": total_moved,
                        "msg": f"第 {batch+1} 批插入失败：{insert_rs.error}"}

            del_rs = await src_engine.execute(db_name=src_db, sql=delete_sql)
            if del_rs.error:
                return {"success": False, "total_moved": total_moved,
                        "msg": f"第 {batch+1} 批删除源数据失败：{del_rs.error}（已插入目标表，需手动处理重复数据）"}

            total_moved += len(rs.rows)
            if len(rs.rows) < batch_size:
                break
            if sleep_ms > 0:
                await asyncio.sleep(sleep_ms / 1000)

        return {"success": True, "mode": "dest", "total_moved": total_moved,
                "msg": f"归档完成，共迁移 {total_moved} 行至 {dest_db}.{dest_table}"}

    @staticmethod
    async def _dest_mongo(
        src_engine: Any, dest_engine: Any,
        src_db: str, src_col: str, condition: str,
        dest_db: str, dest_col: str,
        batch_size: int, sleep_ms: int,
    ) -> dict:
        """MongoDB dest 模式。"""
        import json
        try:
            filter_dict = json.loads(condition)
        except Exception:
            return {"success": False, "msg": "MongoDB 归档条件需为合法 JSON"}

        total_moved = 0
        try:
            src_client = await src_engine.get_connection(src_db)
            dest_client = await dest_engine.get_connection(dest_db)
            src_collection = src_client[src_db][src_col]
            dest_collection = dest_client[dest_db][dest_col]

            for _ in range(10000):
                docs = await src_collection.find(filter_dict).limit(batch_size).to_list(batch_size)
                if not docs:
                    break
                await dest_collection.insert_many(docs)
                ids = [doc["_id"] for doc in docs]
                await src_collection.delete_many({"_id": {"$in": ids}})
                total_moved += len(docs)
                if len(docs) < batch_size:
                    break
                if sleep_ms > 0:
                    await asyncio.sleep(sleep_ms / 1000)
        except Exception as e:
            return {"success": False, "total_moved": total_moved, "msg": str(e)}

        return {"success": True, "mode": "dest", "total_moved": total_moved,
                "msg": f"MongoDB 归档完成，共迁移 {total_moved} 条文档"}

    @staticmethod
    def _quote_cols(columns: list[str], db_type: str) -> str:
        """按数据库类型引用列名。"""
        if db_type in ("pgsql", "oracle", "mssql"):
            return ", ".join(f'"{c}"' for c in columns)
        return ", ".join(f"`{c}`" for c in columns)
