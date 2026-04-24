"""
SQL 回滚辅助服务（Pack E）。

设计原则：
1. 基于 sqlglot 解析工单 SQL，生成逆向语句（适用所有数据库）
2. MySQL/TiDB 额外提供 my2sql 命令生成器（用户自行安装工具）
3. 不同数据库的底层日志回滚需使用专业工具（说明文档）

三种回滚策略：
  A. sqlglot 静态分析（所有数据库）
     - DELETE → INSERT（需要先查原数据，生成模板）
     - INSERT → DELETE（根据主键）
     - UPDATE → UPDATE（逆向赋值，需要先查原值）
     - DDL → 提示手动处理

  B. MySQL/TiDB Binlog 命令生成器
     - 生成 my2sql 调用命令，用户自行在数据库服务器执行

  C. PostgreSQL WAL 查询
     - 通过 pg_logical_slot_get_changes 查询变更记录

  D. 其他数据库
     - 返回对应工具使用说明
"""
from __future__ import annotations

import logging

import sqlglot
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)

# 各数据库回滚支持说明
ROLLBACK_GUIDE: dict[str, dict] = {
    "mysql": {
        "strategy": "binlog",
        "tool": "my2sql",
        "desc": "MySQL 支持通过 Binlog 生成精确回滚 SQL，需安装 my2sql 工具",
        "install": "https://github.com/liuhr/my2sql",
    },
    "tidb": {
        "strategy": "binlog",
        "tool": "my2sql",
        "desc": "TiDB 兼容 MySQL Binlog 格式，可使用 my2sql 工具",
        "install": "https://github.com/liuhr/my2sql",
    },
    "pgsql": {
        "strategy": "wal",
        "tool": "pg_logical / wal2json",
        "desc": "PostgreSQL 可通过 WAL 逻辑复制槽查询变更记录",
        "install": "https://github.com/eulerto/wal2json",
    },
    "oracle": {
        "strategy": "logminer",
        "tool": "LogMiner",
        "desc": "Oracle 使用 LogMiner（DBMS_LOGMNR）分析 Redo Log",
        "install": "Oracle 内置，需 DBA 权限执行 DBMS_LOGMNR 包",
    },
    "mssql": {
        "strategy": "transaction_log",
        "tool": "ApexSQL Log / fn_dblog",
        "desc": "SQL Server 可通过 fn_dblog 或 ApexSQL Log 分析事务日志",
        "install": "fn_dblog 为内置函数，ApexSQL 为商业工具",
    },
    "mongo": {
        "strategy": "oplog",
        "tool": "oplog",
        "desc": "MongoDB 可通过 oplog 集合查询操作历史",
        "install": "需副本集模式，查询 local.oplog.rs 集合",
    },
    "clickhouse": {
        "strategy": "unsupported",
        "tool": "",
        "desc": "ClickHouse 为 append-only 设计，MergeTree 引擎不支持事务回滚",
        "install": "",
    },
    "redis": {
        "strategy": "aof",
        "tool": "AOF 日志",
        "desc": "Redis 可通过 AOF 日志手动恢复，或使用 RDB 快照回滚到某个时间点",
        "install": "需开启 AOF 持久化（appendonly yes）",
    },
    "elasticsearch": {
        "strategy": "snapshot",
        "tool": "Snapshot/Restore",
        "desc": "Elasticsearch 使用 Snapshot/Restore API 恢复到某个快照",
        "install": "内置 API：PUT /_snapshot / POST /_snapshot/{repo}/{snap}/_restore",
    },
}


class RollbackService:
    """SQL 回滚辅助服务。"""

    @staticmethod
    def get_rollback_guide(db_type: str) -> dict:
        """获取指定数据库的回滚工具说明。"""
        return ROLLBACK_GUIDE.get(db_type.lower(), {
            "strategy": "unknown",
            "tool": "",
            "desc": f"{db_type} 的回滚方案请参考官方文档",
            "install": "",
        })

    @staticmethod
    def generate_reverse_sql(
        sql: str,
        db_type: str,
        table_name: str = "",
        primary_keys: list[str] | None = None,
    ) -> dict:
        """
        基于 sqlglot 静态分析生成逆向 SQL 模板。

        注意：
        - DELETE 的逆向是 INSERT，但需要原始数据，此处生成模板供参考
        - UPDATE 的逆向是 UPDATE，但需要原始字段值，此处生成结构模板
        - DDL 的逆向需要人工处理
        """
        dialect_map = {
            "mysql": "mysql", "tidb": "mysql", "starrocks": "mysql", "doris": "mysql",
            "pgsql": "postgres", "oracle": "oracle", "mssql": "tsql",
            "clickhouse": "clickhouse",
        }
        dialect = dialect_map.get(db_type.lower(), "mysql")
        pks = primary_keys or ["id"]

        results = []
        warnings = []

        try:
            stmts = sqlglot.parse(sql, dialect=dialect)
        except Exception as e:
            return {"success": False, "msg": f"SQL 解析失败：{str(e)}", "reverse_sqls": []}

        for stmt in stmts:
            if stmt is None:
                continue

            stmt_type = type(stmt).__name__

            # ── INSERT → DELETE ──────────────────────────────
            if isinstance(stmt, exp.Insert):
                tbl = stmt.find(exp.Table)
                tbl_name = tbl.name if tbl else table_name
                reverse = (
                    f"-- 逆向：删除刚插入的数据（需要知道插入的主键值）\n"
                    f"DELETE FROM {tbl_name} WHERE {pks[0]} = <刚插入的主键值>;"
                )
                results.append({
                    "original": str(stmt),
                    "reverse": reverse,
                    "type": "INSERT→DELETE",
                    "note": "需要知道刚插入记录的主键值",
                })

            # ── DELETE → INSERT ──────────────────────────────
            elif isinstance(stmt, exp.Delete):
                tbl = stmt.find(exp.Table)
                tbl_name = tbl.name if tbl else table_name
                where = stmt.find(exp.Where)
                where_str = str(where).replace("WHERE ", "") if where else "<条件>"
                reverse = (
                    f"-- 逆向：恢复被删除的数据\n"
                    f"-- 1. 先从备份/归档表中查出原始数据：\n"
                    f"--    SELECT * FROM {tbl_name}_backup WHERE {where_str};\n"
                    f"-- 2. 将查出的数据 INSERT 回原表：\n"
                    f"INSERT INTO {tbl_name} (...列名...) VALUES (...原始数据...);"
                )
                results.append({
                    "original": str(stmt),
                    "reverse": reverse,
                    "type": "DELETE→INSERT",
                    "note": "需要从备份源恢复原始数据",
                })

            # ── UPDATE → UPDATE ──────────────────────────────
            elif isinstance(stmt, exp.Update):
                tbl = stmt.find(exp.Table)
                tbl_name = tbl.name if tbl else table_name
                where = stmt.find(exp.Where)
                where_str = str(where).replace("WHERE ", "") if where else "<条件>"

                # 提取被更新的列名
                updated_cols = []
                for eq in stmt.find_all(exp.EQ):
                    if isinstance(eq.left, exp.Column):
                        updated_cols.append(eq.left.name)

                set_clause = ", ".join(
                    f"{col} = <{col}的原始值>" for col in updated_cols
                ) if updated_cols else "<列名> = <原始值>"

                reverse = (
                    f"-- 逆向：将以下字段恢复为原始值\n"
                    f"-- 1. 先查出原始值：\n"
                    f"--    SELECT {', '.join(updated_cols) if updated_cols else '*'} "
                    f"FROM {tbl_name} WHERE {where_str};\n"
                    f"-- 2. 执行回滚 UPDATE：\n"
                    f"UPDATE {tbl_name} SET {set_clause} WHERE {where_str};"
                )
                results.append({
                    "original": str(stmt),
                    "reverse": reverse,
                    "type": "UPDATE→UPDATE",
                    "note": f"需要原始字段值，涉及列：{', '.join(updated_cols)}",
                })

            # ── DDL ──────────────────────────────────────────
            elif isinstance(
                stmt,
                tuple(
                    ddl_type
                    for ddl_type in (
                        exp.Create,
                        exp.Drop,
                        getattr(exp, "AlterTable", None),
                        getattr(exp, "Alter", None),
                    )
                    if ddl_type is not None
                ),
            ):
                results.append({
                    "original": str(stmt),
                    "reverse": "-- DDL 操作需要人工处理，无法自动生成逆向 SQL\n-- 建议：执行前先备份表结构和数据",
                    "type": "DDL→手动",
                    "note": "DDL 操作不可自动回滚，请确保有备份",
                })
                warnings.append("包含 DDL 操作，回滚需要人工处理")

            else:
                results.append({
                    "original": str(stmt),
                    "reverse": f"-- {stmt_type} 语句暂不支持自动生成逆向 SQL",
                    "type": f"{stmt_type}→手动",
                    "note": "请参考数据库文档手动回滚",
                })

        return {
            "success": True,
            "db_type": db_type,
            "dialect": dialect,
            "total": len(results),
            "reverse_sqls": results,
            "warnings": warnings,
            "guide": RollbackService.get_rollback_guide(db_type),
        }

    @staticmethod
    def generate_my2sql_command(
        host: str,
        port: int,
        user: str,
        start_time: str,
        stop_time: str,
        databases: str = "",
        tables: str = "",
        sql_types: str = "insert,update,delete",
        output_dir: str = "/tmp/rollback",
    ) -> dict:
        """
        生成 my2sql 回滚命令（MySQL/TiDB 专用）。
        用户在数据库服务器上执行此命令获取回滚 SQL。
        """
        cmd_parts = [
            "my2sql",
            f"-host {host}",
            f"-port {port}",
            f"-user {user}",
            "-password '<密码>'",
            "-work-type rollback",
            f"-start-datetime '{start_time}'",
            f"-stop-datetime '{stop_time}'",
            f"-sql-types {sql_types}",
            f"-output-dir {output_dir}",
        ]
        if databases:
            cmd_parts.append(f"-databases {databases}")
        if tables:
            cmd_parts.append(f"-tables {tables}")

        cmd = " \\\n  ".join(cmd_parts)

        return {
            "tool": "my2sql",
            "install_url": "https://github.com/liuhr/my2sql",
            "command": cmd,
            "output_dir": output_dir,
            "steps": [
                "1. 在 MySQL 服务器上安装 my2sql",
                f"2. 执行以下命令：\n{cmd}",
                f"3. 在 {output_dir} 目录下找到生成的回滚 SQL 文件",
                "4. 检查 SQL 内容后手动执行回滚",
            ],
            "note": "my2sql 需要 MySQL Binlog 格式为 ROW，且用户需要 REPLICATION SLAVE 权限",
        }

    @staticmethod
    def get_pg_wal_query(
        slot_name: str = "rollback_slot",
        start_lsn: str = "",
    ) -> dict:
        """
        生成 PostgreSQL WAL 查询语句。
        使用 pg_logical_slot_get_changes 读取逻辑复制槽中的变更记录。
        """
        create_slot = (
            f"-- 1. 创建逻辑复制槽（需要 SUPERUSER 权限）\n"
            f"SELECT pg_create_logical_replication_slot('{slot_name}', 'wal2json');"
        )
        query_changes = (
            f"-- 2. 查询变更记录\n"
            f"SELECT * FROM pg_logical_slot_get_changes(\n"
            f"    '{slot_name}', NULL, NULL,\n"
            f"    'pretty-print', '1',\n"
            f"    'include-timestamp', '1'\n"
            f");"
        )
        drop_slot = (
            f"-- 3. 使用完后删除槽（重要！槽不删除会导致 WAL 堆积）\n"
            f"SELECT pg_drop_replication_slot('{slot_name}');"
        )

        return {
            "tool": "pg_logical / wal2json",
            "prereq": "需要安装 wal2json 插件，postgresql.conf 中设置 wal_level = logical",
            "steps": [create_slot, query_changes, drop_slot],
            "note": "推荐提前创建复制槽，而非事后查询（事后创建无法获取历史变更）",
        }
