"""为 ECS 测试引擎生成可重复的观测负载。

脚本从平台数据库读取活跃 Sagitta Control 实例，并对下面的专用测试对象
生成小批量 DML/查询负载；预期由后端容器中的 cron 调用。
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import decrypt_field
from app.models.instance import Instance

TABLE_NAME = "sagitta_observe_events"
IDX_BUCKET = "idx_sag_obs_bucket"
REDIS_PREFIX = "sagitta:observe"
SUPPORTED_TYPES = {"mysql", "pgsql", "redis", "starrocks", "mssql", "tidb", "oracle"}
REAL_WORKLOAD_DB = os.getenv("OBS_REAL_WORKLOAD_DB", os.getenv("OBS_MYSQL_WORKLOAD_DB", "rd_testdb"))
REAL_WORKLOAD_TABLE = os.getenv(
    "OBS_REAL_WORKLOAD_TABLE",
    os.getenv("OBS_MYSQL_WORKLOAD_TABLE", "idp_task_flow_record"),
)
REAL_WORKLOAD_MARKER = os.getenv(
    "OBS_REAL_WORKLOAD_MARKER",
    os.getenv("OBS_MYSQL_WORKLOAD_MARKER", "SagittaWorkload"),
)
BASE_ROWS = int(os.getenv("OBS_BASE_ROWS", "20000"))
BASE_ROWS_SMALL = int(os.getenv("OBS_BASE_ROWS_SMALL", "8000"))
BASE_ROWS_STARROCKS = int(os.getenv("OBS_BASE_ROWS_STARROCKS", "3000"))
SEED_BATCH_ROWS = int(os.getenv("OBS_SEED_BATCH_ROWS", "1000"))
WORKLOAD_ROWS = int(os.getenv("OBS_WORKLOAD_ROWS", "32"))
SLOW_SECONDS = float(os.getenv("OBS_SLOW_SECONDS", "2.2"))
REAL_WORKLOAD_KEEP_DAYS = int(os.getenv("OBS_REAL_WORKLOAD_KEEP_DAYS", "2"))

warnings.filterwarnings("ignore", message=".*database exists.*")
warnings.filterwarnings("ignore", message=".*Table .* already exists.*")


@dataclass(frozen=True)
class Target:
    id: int
    name: str
    db_type: str
    host: str
    port: int
    db_name: str
    user: str
    password: str


def ident_mysql(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Unsafe MySQL identifier: {name!r}")
    return f"`{name}`"


def ident_mssql(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Unsafe MSSQL identifier: {name!r}")
    return f"[{name}]"


def ident_pg(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Unsafe PostgreSQL identifier: {name!r}")
    return f'"{name}"'


def esc_sql(value: str) -> str:
    return value.replace("'", "''")


async def insert_starrocks_rows(cur: Any, rows: list[tuple[int, int, str, float]], chunk_size: int = 500) -> None:
    for offset in range(0, len(rows), chunk_size):
        chunk = rows[offset : offset + chunk_size]
        values = ", ".join(
            f"({row_id}, {bucket}, '{esc_sql(payload)}', {amount}, NOW(), NOW())"
            for row_id, bucket, payload, amount in chunk
        )
        await cur.execute(
            f"""
            INSERT INTO {TABLE_NAME}
                (id, bucket, payload, amount, updated_at, created_at)
            VALUES {values}
            """
        )


def base_row_target(target: Target) -> int:
    if target.db_type == "starrocks":
        return BASE_ROWS_STARROCKS
    if target.db_type in {"oracle", "starrocks", "mssql"}:
        return BASE_ROWS_SMALL
    return BASE_ROWS


def workload_values(target: Target, count: int = WORKLOAD_ROWS) -> list[tuple[int, int, str, float]]:
    base = int(time.time() * 1000) * 100 + target.id * 1_000_000
    return [
        (
            base + idx,
            (base + idx) % 16,
            f"sagitta-workload-{target.db_type}-{base}-{idx}",
            round(random.uniform(10, 500), 2),
        )
        for idx in range(count)
    ]


def seed_values(target: Target, count: int) -> list[tuple[int, int, str, float]]:
    base = int(time.time() * 1000) * 100 + target.id * 1_000_000 + 50_000
    return [
        (
            base + idx,
            (base + idx) % 16,
            f"sagitta-seed-{target.db_type}-{base}-{idx}",
            round(random.uniform(1, 1000), 2),
        )
        for idx in range(count)
    ]


def real_workload_rows(target: Target, count: int = WORKLOAD_ROWS) -> list[dict[str, Any]]:
    base = int(time.time() * 1000) * 100 + target.id * 1_000_000
    marker = REAL_WORKLOAD_MARKER[:32]
    events = [
        "CREATE_RELEASE_BRANCH",
        "CREATE_MERGE_REQUEST",
        "ACCEPT_MERGE_REQUEST",
        "BUILD_PACKAGE",
        "DEPLOY_TEST_ENV",
    ]
    node_states = ["IN_PROGRESS", "SUCCESS", "FAILED"]
    child_states = ["PENDING", "RUNNING", "SUCCESS", "FAILED"]
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        row_id = base + idx
        event = events[idx % len(events)]
        rows.append(
            {
                "id": row_id,
                "task_id": 10_000_000 + ((row_id // 1000) % 900_000),
                "execution_id": f"OBS-{target.db_type}-{row_id}",
                "node_id": 1000 + idx,
                "child_node_id": f"node-{row_id % 10000}",
                "child_node_state": child_states[(row_id + idx) % len(child_states)],
                "node_state": node_states[(row_id + idx) % len(node_states)],
                "event": event,
                "detail": f"Sagitta Control observability workload tick={base}, event={event}, seq={idx}",
                "create_name": marker,
                "update_name": marker,
                "is_deleted": 0,
                "create_code": "sagitta-observe",
                "update_code": "sagitta-observe",
                "remark": "observability workload",
            }
        )
    return rows


def real_mysql_values(rows: list[dict[str, Any]], include_id: bool) -> list[tuple[Any, ...]]:
    values = []
    for row in rows:
        item = (
            row["task_id"],
            row["execution_id"],
            row["node_id"],
            row["child_node_id"],
            row["child_node_state"],
            row["node_state"],
            row["event"],
            row["detail"],
            row["create_name"],
            row["update_name"],
            row["is_deleted"],
            row["create_code"],
            row["update_code"],
            row["remark"],
        )
        values.append((row["id"], *item) if include_id else item)
    return values


async def mysql_table_exists(cur: Any, db_name: str, table_name: str) -> bool:
    await cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (db_name, table_name),
    )
    return int((await cur.fetchone())[0] or 0) > 0


async def load_targets() -> list[Target]:
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(Instance)
                    .where(Instance.is_active.is_(True), Instance.db_type.in_(SUPPORTED_TYPES))
                    .order_by(Instance.id)
                )
            ).scalars().all()
            return [
                Target(
                    id=inst.id,
                    name=inst.instance_name,
                    db_type=inst.db_type.lower(),
                    host=inst.host,
                    port=inst.port or 0,
                    db_name=inst.db_name or "",
                    user=decrypt_field(inst.user),
                    password=decrypt_field(inst.password),
                )
                for inst in rows
            ]
    finally:
        await engine.dispose()


async def run_mysql_like_idp_task_flow_record(cur: Any, target: Target, flavor: str) -> dict[str, Any]:
    db_name = REAL_WORKLOAD_DB
    table_name = REAL_WORKLOAD_TABLE
    marker = REAL_WORKLOAD_MARKER[:32]
    table_ref = ident_mysql(table_name)
    rows = real_workload_rows(target)
    include_id = flavor == "starrocks"
    ops = 0
    warnings: list[str] = []
    await cur.execute(f"USE {ident_mysql(db_name)}")

    id_column = "id, " if include_id else ""
    id_placeholder = "%s, " if include_id else ""
    await cur.executemany(
        f"""
        INSERT INTO {table_ref}
            ({id_column}task_id, execution_id, node_id, child_node_id, child_node_state,
             node_state, event, detail, create_name, create_time, update_name,
             update_time, is_deleted, create_code, update_code, remark)
        VALUES
            ({id_placeholder}%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW(), %s, %s, %s, %s)
        """,
        real_mysql_values(rows, include_id),
    )
    ops += len(rows)

    try:
        if flavor == "starrocks":
            await cur.execute(
                f"""
                SELECT id, task_id, event, node_state, update_time
                FROM {table_ref}
                WHERE execution_id = %s
                LIMIT 1
                """,
                (rows[-1]["execution_id"],),
            )
            await cur.fetchall()
            ops += 1
        else:
            await cur.execute(
                f"""
                UPDATE {table_ref}
                SET node_state = 'SUCCESS',
                    child_node_state = 'SUCCESS',
                    update_name = %s,
                    update_time = NOW(),
                    remark = 'observability workload updated'
                WHERE execution_id = %s
                LIMIT 1
                """,
                (marker, rows[-1]["execution_id"]),
            )
            await cur.execute(
                f"""
                UPDATE {table_ref}
                SET update_time = NOW(),
                    detail = CONCAT(LEFT(COALESCE(detail, ''), 180), ' | tick=', %s)
                WHERE create_name = %s
                ORDER BY id DESC
                LIMIT 50
                """,
                (rows[0]["id"], marker),
            )
            ops += 2
    except Exception as exc:
        warnings.append(f"real-table update skipped: {exc}")

    await cur.execute(
        f"""
        SELECT task_id, COUNT(*) AS cnt, MAX(update_time) AS last_update
        FROM {table_ref}
        WHERE task_id = %s
        GROUP BY task_id
        """,
        (rows[0]["task_id"],),
    )
    await cur.fetchall()
    await cur.execute(
        f"""
        SELECT event, node_state, COUNT(*) AS cnt
        FROM {table_ref}
        WHERE create_name = %s
          AND update_time >= NOW() - INTERVAL 10 MINUTE
        GROUP BY event, node_state
        ORDER BY cnt DESC
        LIMIT 8
        """,
        (marker,),
    )
    await cur.fetchall()
    ops += 2

    try:
        if flavor == "starrocks":
            pass
        else:
            await cur.execute(
                f"""
                DELETE FROM {table_ref}
                WHERE create_name = %s
                  AND create_time < NOW() - INTERVAL %s DAY
                LIMIT 500
                """,
                (marker, REAL_WORKLOAD_KEEP_DAYS),
            )
            ops += 1
    except Exception as exc:
        warnings.append(f"real-table cleanup skipped: {exc}")

    try:
        await cur.execute(f"SELECT SLEEP({SLOW_SECONDS})")
        await cur.fetchall()
        ops += 1
    except Exception as exc:
        warnings.append(f"sleep query skipped: {exc}")
    result: dict[str, Any] = {"status": "ok", "ops": ops, "table": f"{db_name}.{table_name}"}
    if warnings:
        result["warnings"] = warnings
    return result


async def run_mysql_family(target: Target, flavor: str) -> dict[str, Any]:
    import aiomysql

    db_name = target.db_name or "test"
    conn = await aiomysql.connect(
        host=target.host,
        port=target.port,
        user=target.user,
        password=target.password,
        autocommit=True,
        charset="utf8mb4",
        connect_timeout=10,
    )
    ops = 0
    warnings: list[str] = []
    try:
        async with conn.cursor() as cur:
            if (
                REAL_WORKLOAD_DB
                and REAL_WORKLOAD_TABLE
                and flavor in {"mysql", "tidb", "starrocks"}
            ):
                if not await mysql_table_exists(cur, REAL_WORKLOAD_DB, REAL_WORKLOAD_TABLE):
                    return {
                        "status": "error",
                        "error": f"{REAL_WORKLOAD_DB}.{REAL_WORKLOAD_TABLE} not found",
                    }
                return await run_mysql_like_idp_task_flow_record(cur, target, flavor)

            await cur.execute(f"CREATE DATABASE IF NOT EXISTS {ident_mysql(db_name)}")
            await cur.execute(f"USE {ident_mysql(db_name)}")
            if flavor == "starrocks":
                await cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                        id BIGINT NOT NULL,
                        bucket INT NOT NULL,
                        payload VARCHAR(255),
                        amount DECIMAL(12, 2),
                        updated_at DATETIME,
                        created_at DATETIME
                    )
                    PRIMARY KEY(id)
                    DISTRIBUTED BY HASH(id) BUCKETS 4
                    PROPERTIES ("replication_num" = "1")
                    """
                )
            else:
                await cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ident_mysql(TABLE_NAME)} (
                        id BIGINT PRIMARY KEY,
                        bucket INT NOT NULL,
                        payload VARCHAR(255),
                        amount DECIMAL(12, 2),
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        KEY idx_bucket(bucket),
                        KEY idx_updated_at(updated_at)
                    )
                    """
                )
            ops += 1

            table_ref = TABLE_NAME if flavor == "starrocks" else ident_mysql(TABLE_NAME)
            await cur.execute(f"SELECT COUNT(*) FROM {table_ref}")
            current_rows = int((await cur.fetchone())[0] or 0)
            seed_missing = max(0, base_row_target(target) - current_rows)
            seed_count = min(SEED_BATCH_ROWS, seed_missing)
            if seed_count:
                if flavor == "starrocks":
                    await insert_starrocks_rows(cur, seed_values(target, seed_count))
                else:
                    await cur.executemany(
                        f"""
                        INSERT IGNORE INTO {ident_mysql(TABLE_NAME)}
                            (id, bucket, payload, amount)
                        VALUES (%s, %s, %s, %s)
                        """,
                        seed_values(target, seed_count),
                    )
                ops += seed_count

            rows = workload_values(target)
            if flavor == "starrocks":
                await insert_starrocks_rows(cur, rows)
            else:
                await cur.executemany(
                    f"""
                    INSERT INTO {ident_mysql(TABLE_NAME)}
                        (id, bucket, payload, amount)
                    VALUES (%s, %s, %s, %s)
                    """,
                    rows,
                )
            ops += len(rows)

            bucket = rows[0][1]
            cutoff = rows[-1][0] - 20_000
            if flavor == "starrocks":
                await cur.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET amount = amount + 1, updated_at = NOW()
                    WHERE bucket = %s
                    """,
                    (bucket,),
                )
                await cur.execute(
                    f"""
                    DELETE FROM {TABLE_NAME}
                    WHERE bucket = %s
                      AND id < %s
                      AND payload LIKE 'sagitta-workload%%'
                    """,
                    (bucket, cutoff),
                )
                await cur.execute(
                    f"""
                    SELECT bucket, COUNT(*) AS cnt, SUM(amount) AS total_amount, MAX(payload) AS sample_payload
                    FROM {TABLE_NAME}
                    WHERE payload LIKE '%%sagitta%%' OR amount > 0
                    GROUP BY bucket
                    ORDER BY cnt DESC
                    LIMIT 5
                    """
                )
            else:
                await cur.execute(
                    f"""
                    UPDATE {ident_mysql(TABLE_NAME)}
                    SET amount = amount + 1, payload = CONCAT(payload, ':u')
                    WHERE bucket = %s OR MOD(id, 17) = 0
                    ORDER BY id DESC
                    LIMIT 500
                    """,
                    (bucket,),
                )
                await cur.execute(
                    f"""
                    DELETE FROM {ident_mysql(TABLE_NAME)}
                    WHERE id < %s
                      AND MOD(id, 11) = 0
                      AND payload LIKE 'sagitta-workload%%'
                    LIMIT 80
                    """,
                    (cutoff,),
                )
                await cur.execute(
                    f"""
                    SELECT bucket, COUNT(*) AS cnt, SUM(amount) AS total_amount, MAX(payload) AS sample_payload
                    FROM {ident_mysql(TABLE_NAME)}
                    WHERE payload LIKE '%%workload%%' OR amount > 0
                    GROUP BY bucket
                    ORDER BY cnt DESC
                    LIMIT 8
                    """
                )
            await cur.fetchall()
            ops += 3

            try:
                await cur.execute(f"SELECT SLEEP({SLOW_SECONDS})")
                await cur.fetchall()
                ops += 1
            except Exception as exc:
                warnings.append(f"sleep query skipped: {exc}")
    finally:
        conn.close()
    return {"status": "ok", "ops": ops, "warnings": warnings}


async def run_pgsql_idp_task_flow_record(conn: Any, target: Target) -> dict[str, Any]:
    table_ref = f"public.{ident_pg(REAL_WORKLOAD_TABLE)}"
    rows = real_workload_rows(target)
    values = [
        (
            row["id"],
            row["task_id"],
            row["execution_id"],
            row["node_id"],
            row["child_node_id"],
            row["child_node_state"],
            row["node_state"],
            row["event"],
            row["detail"],
            row["create_name"],
            row["update_name"],
            row["is_deleted"],
            row["create_code"],
            row["update_code"],
            row["remark"],
        )
        for row in rows
    ]
    await conn.executemany(
        f"""
        INSERT INTO {table_ref}
            (id, task_id, execution_id, node_id, child_node_id, child_node_state,
             node_state, event, detail, create_name, create_time, update_name,
             update_time, is_deleted, create_code, update_code, remark)
        VALUES
            ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now(), $11, now(), $12, $13, $14, $15)
        """,
        values,
    )
    await conn.execute(
        f"""
        UPDATE {table_ref}
        SET node_state = 'SUCCESS',
            child_node_state = 'SUCCESS',
            update_name = $1,
            update_time = now(),
            remark = 'observability workload updated'
        WHERE execution_id = $2
        """,
        REAL_WORKLOAD_MARKER[:32],
        rows[-1]["execution_id"],
    )
    await conn.execute(
        f"""
        WITH picked AS (
            SELECT id
            FROM {table_ref}
            WHERE create_name = $1
            ORDER BY id DESC
            LIMIT 50
        )
        UPDATE {table_ref} t
        SET update_time = now(),
            detail = left(coalesce(t.detail, ''), 180) || ' | tick=' || $2::text
        FROM picked
        WHERE t.id = picked.id
        """,
        REAL_WORKLOAD_MARKER[:32],
        str(rows[0]["id"]),
    )
    await conn.fetch(
        f"""
        SELECT task_id, COUNT(*) AS cnt, MAX(update_time) AS last_update
        FROM {table_ref}
        WHERE task_id = $1
        GROUP BY task_id
        """,
        rows[0]["task_id"],
    )
    await conn.fetch(
        f"""
        SELECT event, node_state, COUNT(*) AS cnt
        FROM {table_ref}
        WHERE create_name = $1
          AND update_time >= now() - interval '10 minutes'
        GROUP BY event, node_state
        ORDER BY cnt DESC
        LIMIT 8
        """,
        REAL_WORKLOAD_MARKER[:32],
    )
    await conn.execute(
        f"""
        WITH doomed AS (
            SELECT id
            FROM {table_ref}
            WHERE create_name = $1
              AND create_time < now() - ($2::int * interval '1 day')
            LIMIT 500
        )
        DELETE FROM {table_ref}
        WHERE id IN (SELECT id FROM doomed)
        """,
        REAL_WORKLOAD_MARKER[:32],
        REAL_WORKLOAD_KEEP_DAYS,
    )
    await conn.fetch("SELECT pg_sleep($1)", SLOW_SECONDS)
    return {"status": "ok", "ops": len(rows) + 6, "table": f"{REAL_WORKLOAD_DB}.{REAL_WORKLOAD_TABLE}"}


async def run_pgsql(target: Target) -> dict[str, Any]:
    import asyncpg

    if REAL_WORKLOAD_DB and REAL_WORKLOAD_TABLE:
        conn = await asyncpg.connect(
            host=target.host,
            port=target.port,
            user=target.user,
            password=target.password,
            database=REAL_WORKLOAD_DB,
            timeout=10,
        )
        try:
            exists = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
                """,
                REAL_WORKLOAD_TABLE,
            )
            if not int(exists or 0):
                return {
                    "status": "error",
                    "error": f"{REAL_WORKLOAD_DB}.{REAL_WORKLOAD_TABLE} not found",
                }
            return await run_pgsql_idp_task_flow_record(conn, target)
        finally:
            await conn.close()

    conn = await asyncpg.connect(
        host=target.host,
        port=target.port,
        user=target.user,
        password=target.password,
        database=target.db_name or "postgres",
        timeout=10,
    )
    ops = 0
    try:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id BIGINT PRIMARY KEY,
                bucket INT NOT NULL,
                payload TEXT,
                amount NUMERIC(12, 2),
                updated_at TIMESTAMPTZ DEFAULT now(),
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        await conn.execute(
            f"CREATE INDEX IF NOT EXISTS {IDX_BUCKET} ON {TABLE_NAME}(bucket)"
        )
        ops += 2
        current_rows = await conn.fetchval(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        seed_missing = max(0, base_row_target(target) - int(current_rows or 0))
        seed_count = min(SEED_BATCH_ROWS, seed_missing)
        if seed_count:
            await conn.executemany(
                f"""
                INSERT INTO {TABLE_NAME} (id, bucket, payload, amount)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO NOTHING
                """,
                seed_values(target, seed_count),
            )
            ops += seed_count
        rows = workload_values(target)
        for row_id, bucket, payload, amount in rows:
            await conn.execute(
                f"""
                INSERT INTO {TABLE_NAME} (id, bucket, payload, amount)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    amount = EXCLUDED.amount,
                    updated_at = now()
                """,
                row_id,
                bucket,
                payload,
                amount,
            )
            ops += 1
        await conn.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET amount = amount + 1, payload = payload || ':u', updated_at = now()
            WHERE bucket = $1 OR id % 17 = 0
            """,
            rows[0][1],
        )
        await conn.execute(
            f"""
            DELETE FROM {TABLE_NAME}
            WHERE id IN (
                SELECT id
                FROM {TABLE_NAME}
                WHERE id < $1
                  AND id % 11 = 0
                  AND payload LIKE 'sagitta-workload%'
                LIMIT 80
            )
            """,
            rows[-1][0] - 20_000,
        )
        await conn.fetch(
            f"""
            SELECT bucket, COUNT(*) AS cnt, SUM(amount) AS total_amount, MAX(payload) AS sample_payload
            FROM {TABLE_NAME}
            WHERE payload LIKE '%workload%' OR amount > 0
            GROUP BY bucket
            ORDER BY cnt DESC
            LIMIT 8
            """
        )
        await conn.fetch("SELECT pg_sleep($1)", SLOW_SECONDS)
        ops += 4
    finally:
        await conn.close()
    return {"status": "ok", "ops": ops}


async def run_redis(target: Target) -> dict[str, Any]:
    import redis.asyncio as aioredis

    db_index = int(target.db_name) if target.db_name.isdigit() else 0
    client = aioredis.Redis(
        host=target.host,
        port=target.port,
        username=target.user or None,
        password=target.password or None,
        db=db_index,
        decode_responses=True,
        socket_connect_timeout=10,
    )
    warnings: list[str] = []
    ops = 0
    try:
        try:
            await client.config_set("slowlog-log-slower-than", 0)
            await client.config_set("slowlog-max-len", 256)
            ops += 2
        except Exception as exc:
            warnings.append(f"slowlog config skipped: {exc}")

        seed_set = f"{REDIS_PREFIX}:seed:set"
        current_rows = int(await client.scard(seed_set) or 0)
        seed_missing = max(0, base_row_target(target) - current_rows)
        seed_count = min(SEED_BATCH_ROWS, seed_missing)
        if seed_count:
            pipe = client.pipeline(transaction=False)
            for row_id, bucket, payload, amount in seed_values(target, seed_count):
                key = f"{REDIS_PREFIX}:seed:{row_id}"
                pipe.hset(
                    key,
                    mapping={
                        "bucket": bucket,
                        "payload": payload,
                        "amount": amount,
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                )
                pipe.sadd(seed_set, key)
                pipe.zadd(f"{REDIS_PREFIX}:seed:zset", {key: row_id})
            await pipe.execute()
            ops += seed_count * 3

        base = int(time.time() * 1000) + target.id * 100_000
        key = f"{REDIS_PREFIX}:hash:{base}"
        list_key = f"{REDIS_PREFIX}:list"
        zset_key = f"{REDIS_PREFIX}:zset"
        pipe = client.pipeline(transaction=False)
        for idx in range(WORKLOAD_ROWS):
            row_key = f"{key}:{idx}"
            pipe.hset(row_key, mapping={"payload": f"redis-{base}-{idx}", "amount": str((base + idx) % 1000)})
            pipe.expire(row_key, 3600)
            pipe.lpush(list_key, row_key)
            pipe.zadd(zset_key, {row_key: base + idx})
        pipe.incrby(f"{REDIS_PREFIX}:counter", WORKLOAD_ROWS)
        pipe.ltrim(list_key, 0, 5000)
        pipe.zremrangebyrank(zset_key, 0, -5001)
        await pipe.execute()
        await client.zrange(zset_key, -200, -1, withscores=True)
        await client.sort(list_key, start=0, num=100, alpha=True)
        await client.eval("local s=0 for i=1,200000 do s=s+i end return s", 0)
        await client.delete(f"{REDIS_PREFIX}:delete:{base - 17}")
        ops += WORKLOAD_ROWS * 4 + 6
    finally:
        await client.aclose()
    return {"status": "ok", "ops": ops, "warnings": warnings}


def run_mssql_idp_task_flow_record(cur: Any, target: Target) -> dict[str, Any]:
    table_ref = f"dbo.{ident_mssql(REAL_WORKLOAD_TABLE)}"
    marker = REAL_WORKLOAD_MARKER[:32]
    rows = real_workload_rows(target)
    ops = 0
    for row in rows:
        cur.execute(
            f"""
            INSERT INTO {table_ref}
                (id, task_id, execution_id, node_id, child_node_id, child_node_state,
                 node_state, event, detail, create_name, create_time, update_name,
                 update_time, is_deleted, create_code, update_code, remark)
            VALUES (
                {row["id"]}, {row["task_id"]}, N'{esc_sql(row["execution_id"])}',
                {row["node_id"]}, N'{esc_sql(row["child_node_id"])}',
                N'{esc_sql(row["child_node_state"])}', N'{esc_sql(row["node_state"])}',
                N'{esc_sql(row["event"])}', N'{esc_sql(row["detail"])}',
                N'{esc_sql(row["create_name"])}', SYSDATETIME(),
                N'{esc_sql(row["update_name"])}', SYSDATETIME(), {row["is_deleted"]},
                N'{esc_sql(row["create_code"])}', N'{esc_sql(row["update_code"])}',
                N'{esc_sql(row["remark"])}'
            )
            """
        )
        ops += 1
    cur.execute(
        f"""
        UPDATE {table_ref}
        SET node_state = N'SUCCESS',
            child_node_state = N'SUCCESS',
            update_name = N'{esc_sql(marker)}',
            update_time = SYSDATETIME(),
            remark = N'observability workload updated'
        WHERE execution_id = N'{esc_sql(rows[-1]["execution_id"])}'
        """
    )
    cur.execute(
        f"""
        UPDATE {table_ref}
        SET update_time = SYSDATETIME(),
            detail = LEFT(ISNULL(detail, N''), 180) + N' | tick={rows[0]["id"]}'
        WHERE id IN (
            SELECT TOP (50) id
            FROM {table_ref}
            WHERE create_name = N'{esc_sql(marker)}'
            ORDER BY id DESC
        )
        """
    )
    cur.execute(
        f"""
        SELECT task_id, COUNT(*) AS cnt, MAX(update_time) AS last_update
        FROM {table_ref}
        WHERE task_id = {rows[0]["task_id"]}
        GROUP BY task_id
        """
    )
    cur.fetchall()
    cur.execute(
        f"""
        SELECT TOP (8) event, node_state, COUNT(*) AS cnt
        FROM {table_ref}
        WHERE create_name = N'{esc_sql(marker)}'
          AND update_time >= DATEADD(minute, -10, SYSDATETIME())
        GROUP BY event, node_state
        ORDER BY cnt DESC
        """
    )
    cur.fetchall()
    cur.execute(
        f"""
        DELETE TOP (500) FROM {table_ref}
        WHERE create_name = N'{esc_sql(marker)}'
          AND create_time < DATEADD(day, -{REAL_WORKLOAD_KEEP_DAYS}, SYSDATETIME())
        """
    )
    cur.execute(f"WAITFOR DELAY '00:00:{max(2, int(SLOW_SECONDS)):02d}'")
    return {"status": "ok", "ops": ops + 6, "table": f"{REAL_WORKLOAD_DB}.dbo.{REAL_WORKLOAD_TABLE}"}


def run_mssql_sync(target: Target) -> dict[str, Any]:
    import pytds

    db_name = REAL_WORKLOAD_DB if REAL_WORKLOAD_DB and REAL_WORKLOAD_TABLE else target.db_name or "test"
    ops = 0
    with pytds.connect(
        server=target.host,
        port=target.port,
        database=db_name,
        user=target.user,
        password=target.password,
        timeout=30,
        login_timeout=10,
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            if REAL_WORKLOAD_DB and REAL_WORKLOAD_TABLE:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = %s
                    """,
                    (REAL_WORKLOAD_TABLE,),
                )
                if int(cur.fetchone()[0] or 0) == 0:
                    return {
                        "status": "error",
                        "error": f"{REAL_WORKLOAD_DB}.dbo.{REAL_WORKLOAD_TABLE} not found",
                    }
                return run_mssql_idp_task_flow_record(cur, target)

            cur.execute(
                f"""
                IF OBJECT_ID(N'dbo.{TABLE_NAME}', N'U') IS NULL
                CREATE TABLE dbo.{TABLE_NAME} (
                    id BIGINT NOT NULL PRIMARY KEY,
                    bucket INT NOT NULL,
                    payload NVARCHAR(255) NULL,
                    amount DECIMAL(12, 2) NULL,
                    updated_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
                    created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
                )
                """
            )
            cur.execute(
                f"""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'{IDX_BUCKET}'
                      AND object_id = OBJECT_ID(N'dbo.{TABLE_NAME}')
                )
                CREATE INDEX {IDX_BUCKET} ON dbo.{TABLE_NAME}(bucket)
                """
            )
            ops += 2
            cur.execute(f"SELECT COUNT(*) FROM dbo.{TABLE_NAME}")
            current_rows = int(cur.fetchone()[0] or 0)
            seed_missing = max(0, base_row_target(target) - current_rows)
            seed_count = min(SEED_BATCH_ROWS, seed_missing)
            for row_id, bucket, payload, amount in seed_values(target, seed_count):
                cur.execute(
                    f"""
                    INSERT INTO dbo.{TABLE_NAME} (id, bucket, payload, amount)
                    VALUES ({row_id}, {bucket}, N'{esc_sql(payload)}', {amount})
                    """
                )
                ops += 1
            rows = workload_values(target)
            for row_id, bucket, payload, amount in rows:
                cur.execute(
                    f"""
                    IF EXISTS (SELECT 1 FROM dbo.{TABLE_NAME} WHERE id = {row_id})
                        UPDATE dbo.{TABLE_NAME}
                        SET bucket = {bucket},
                            payload = N'{esc_sql(payload)}',
                            amount = {amount},
                            updated_at = SYSDATETIME()
                        WHERE id = {row_id}
                    ELSE
                        INSERT INTO dbo.{TABLE_NAME} (id, bucket, payload, amount)
                        VALUES ({row_id}, {bucket}, N'{esc_sql(payload)}', {amount})
                    """
                )
                ops += 1
            cur.execute(
                f"""
                UPDATE TOP (500) dbo.{TABLE_NAME}
                SET amount = amount + 1, updated_at = SYSDATETIME()
                WHERE bucket = {rows[0][1]} OR id % 17 = 0
                """
            )
            cur.execute(
                f"""
                DELETE TOP (80) FROM dbo.{TABLE_NAME}
                WHERE id < {rows[-1][0] - 20000}
                  AND payload LIKE N'sagitta-workload%'
                """
            )
            cur.execute(
                f"""
                SELECT TOP (8) bucket, COUNT(*) AS cnt, SUM(amount) AS total_amount, MAX(payload) AS sample_payload
                FROM dbo.{TABLE_NAME}
                WHERE payload LIKE N'%workload%' OR amount > 0
                GROUP BY bucket
                ORDER BY cnt DESC
                """
            )
            cur.fetchall()
            cur.execute(f"WAITFOR DELAY '00:00:{max(2, int(SLOW_SECONDS)):02d}'")
            ops += 4
    return {"status": "ok", "ops": ops}


def run_oracle_idp_task_flow_record(conn: Any, cur: Any, owner: str, target: Target) -> dict[str, Any]:
    table_ref = f"{owner}.{REAL_WORKLOAD_TABLE.upper()}"
    marker = REAL_WORKLOAD_MARKER[:32]
    rows = real_workload_rows(target)
    cur.executemany(
        f"""
        INSERT INTO {table_ref}
            (id, task_id, execution_id, node_id, child_node_id, child_node_state,
             node_state, event, detail, create_name, create_time, update_name,
             update_time, is_deleted, create_code, update_code, remark)
        VALUES
            (:id, :task_id, :execution_id, :node_id, :child_node_id, :child_node_state,
             :node_state, :event, :detail, :create_name, SYSTIMESTAMP, :update_name,
             SYSTIMESTAMP, :is_deleted, :create_code, :update_code, :remark)
        """,
        rows,
    )
    cur.execute(
        f"""
        UPDATE {table_ref}
        SET node_state = 'SUCCESS',
            child_node_state = 'SUCCESS',
            update_name = :marker,
            update_time = SYSTIMESTAMP,
            remark = 'observability workload updated'
        WHERE execution_id = :execution_id
        """,
        {"marker": marker, "execution_id": rows[-1]["execution_id"]},
    )
    cur.execute(
        f"""
        UPDATE {table_ref}
        SET update_time = SYSTIMESTAMP,
            detail = SUBSTR(NVL(detail, ''), 1, 180) || ' | tick=' || :tick
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id
                FROM {table_ref}
                WHERE create_name = :marker
                ORDER BY id DESC
            )
            WHERE ROWNUM <= 50
        )
        """,
        {"tick": rows[0]["id"], "marker": marker},
    )
    cur.execute(
        f"""
        SELECT task_id, COUNT(*) AS cnt, MAX(update_time) AS last_update
        FROM {table_ref}
        WHERE task_id = :task_id
        GROUP BY task_id
        """,
        {"task_id": rows[0]["task_id"]},
    )
    cur.fetchall()
    cur.execute(
        f"""
        SELECT event, node_state, COUNT(*) AS cnt
        FROM {table_ref}
        WHERE create_name = :marker
          AND update_time >= SYSTIMESTAMP - INTERVAL '10' MINUTE
        GROUP BY event, node_state
        ORDER BY cnt DESC
        """,
        {"marker": marker},
    )
    cur.fetchall()
    cur.execute(
        f"""
        DELETE FROM {table_ref}
        WHERE create_name = :marker
          AND create_time < SYSTIMESTAMP - NUMTODSINTERVAL(:days, 'DAY')
          AND ROWNUM <= 500
        """,
        {"marker": marker, "days": REAL_WORKLOAD_KEEP_DAYS},
    )
    warnings: list[str] = []
    try:
        cur.execute(f"BEGIN DBMS_LOCK.SLEEP({SLOW_SECONDS}); END;")
    except Exception as exc:
        warnings.append(f"sleep skipped: {exc}")
    conn.commit()
    result: dict[str, Any] = {
        "status": "ok",
        "ops": len(rows) + 6,
        "table": f"{owner}.{REAL_WORKLOAD_TABLE.upper()}",
    }
    if warnings:
        result["warnings"] = warnings
    return result


def run_oracle_sync(target: Target) -> dict[str, Any]:
    import oracledb

    from app.engines.oracle import _init_oracle_client_if_needed

    _init_oracle_client_if_needed()
    ops = 0
    warnings: list[str] = []
    dsn = f"{target.host}:{target.port}/{target.db_name or 'XE'}"
    with oracledb.connect(user=target.user, password=target.password, dsn=dsn) as conn:
        with conn.cursor() as cur:
            if REAL_WORKLOAD_DB and REAL_WORKLOAD_TABLE:
                owner = REAL_WORKLOAD_DB.upper()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM all_tables
                    WHERE owner = :owner AND table_name = :table_name
                    """,
                    {"owner": owner, "table_name": REAL_WORKLOAD_TABLE.upper()},
                )
                if int(cur.fetchone()[0] or 0) == 0:
                    return {
                        "status": "error",
                        "error": f"{owner}.{REAL_WORKLOAD_TABLE.upper()} not found",
                    }
                return run_oracle_idp_task_flow_record(conn, cur, owner, target)

            try:
                cur.execute(
                    f"""
                    CREATE TABLE {TABLE_NAME} (
                        id NUMBER(19) PRIMARY KEY,
                        bucket NUMBER(10) NOT NULL,
                        payload VARCHAR2(255),
                        amount NUMBER(12, 2),
                        updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
                    )
                    """
                )
                ops += 1
            except Exception as exc:
                if "ORA-00955" not in str(exc):
                    raise
            try:
                cur.execute(f"CREATE INDEX {IDX_BUCKET} ON {TABLE_NAME}(bucket)")
                ops += 1
            except Exception as exc:
                if "ORA-00955" not in str(exc):
                    warnings.append(f"index create skipped: {exc}")
            cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            current_rows = int(cur.fetchone()[0] or 0)
            seed_missing = max(0, base_row_target(target) - current_rows)
            seed_count = min(SEED_BATCH_ROWS, seed_missing)
            if seed_count:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE_NAME} (id, bucket, payload, amount)
                    VALUES (:id, :bucket, :payload, :amount)
                    """,
                    [
                        {"id": row_id, "bucket": bucket, "payload": payload, "amount": amount}
                        for row_id, bucket, payload, amount in seed_values(target, seed_count)
                    ],
                )
                ops += seed_count
            rows = workload_values(target)
            for row_id, bucket, payload, amount in rows:
                cur.execute(
                    f"""
                    MERGE INTO {TABLE_NAME} t
                    USING (
                        SELECT :id AS id, :bucket AS bucket, :payload AS payload, :amount AS amount
                        FROM dual
                    ) s
                    ON (t.id = s.id)
                    WHEN MATCHED THEN UPDATE SET
                        t.bucket = s.bucket,
                        t.payload = s.payload,
                        t.amount = s.amount,
                        t.updated_at = SYSTIMESTAMP
                    WHEN NOT MATCHED THEN INSERT (id, bucket, payload, amount)
                    VALUES (s.id, s.bucket, s.payload, s.amount)
                    """,
                    {"id": row_id, "bucket": bucket, "payload": payload, "amount": amount},
                )
                ops += 1
            cur.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET amount = amount + 1, updated_at = SYSTIMESTAMP
                WHERE (bucket = :bucket OR MOD(id, 17) = 0)
                  AND ROWNUM <= 500
                """,
                {"bucket": rows[0][1]},
            )
            cur.execute(
                f"""
                DELETE FROM {TABLE_NAME}
                WHERE id < :cutoff
                  AND payload LIKE 'sagitta-workload%'
                  AND ROWNUM <= 80
                """,
                {"cutoff": rows[-1][0] - 20_000},
            )
            cur.execute(
                f"""
                SELECT bucket, COUNT(*) AS cnt, SUM(amount) AS total_amount, MAX(payload) AS sample_payload
                FROM {TABLE_NAME}
                WHERE payload LIKE '%workload%' OR amount > 0
                GROUP BY bucket
                ORDER BY cnt DESC
                """
            )
            cur.fetchall()
            try:
                cur.execute(f"BEGIN DBMS_LOCK.SLEEP({SLOW_SECONDS}); END;")
            except Exception as exc:
                warnings.append(f"sleep skipped: {exc}")
            conn.commit()
            ops += 4
    return {"status": "ok", "ops": ops, "warnings": warnings}


async def run_target(target: Target) -> dict[str, Any]:
    try:
        if target.db_type == "mysql":
            result = await run_mysql_family(target, "mysql")
        elif target.db_type == "tidb":
            result = await run_mysql_family(target, "tidb")
        elif target.db_type == "starrocks":
            result = await run_mysql_family(target, "starrocks")
        elif target.db_type == "pgsql":
            result = await run_pgsql(target)
        elif target.db_type == "redis":
            result = await run_redis(target)
        elif target.db_type == "mssql":
            result = await asyncio.to_thread(run_mssql_sync, target)
        elif target.db_type == "oracle":
            result = await asyncio.to_thread(run_oracle_sync, target)
        else:
            result = {"status": "skipped", "reason": "unsupported"}
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
    return {
        "instance_id": target.id,
        "instance_name": target.name,
        "db_type": target.db_type,
        **result,
    }


async def main() -> None:
    started = datetime.now(UTC)
    targets = await load_targets()
    results = await asyncio.gather(*(run_target(target) for target in targets))
    payload = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "ok": sum(1 for item in results if item.get("status") == "ok"),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
