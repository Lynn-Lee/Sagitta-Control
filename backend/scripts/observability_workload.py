"""Generate repeatable observability workload for the ECS test engines.

The script reads active SagittaDB instances from the platform database and
generates small DML/query workloads against the dedicated test objects below.
It is intended to be run from the backend container by cron.
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
BASE_ROWS = int(os.getenv("OBS_BASE_ROWS", "20000"))
BASE_ROWS_SMALL = int(os.getenv("OBS_BASE_ROWS_SMALL", "8000"))
BASE_ROWS_STARROCKS = int(os.getenv("OBS_BASE_ROWS_STARROCKS", "3000"))
SEED_BATCH_ROWS = int(os.getenv("OBS_SEED_BATCH_ROWS", "1000"))
WORKLOAD_ROWS = int(os.getenv("OBS_WORKLOAD_ROWS", "32"))
SLOW_SECONDS = float(os.getenv("OBS_SLOW_SECONDS", "2.2"))

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


async def run_pgsql(target: Target) -> dict[str, Any]:
    import asyncpg

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


def run_mssql_sync(target: Target) -> dict[str, Any]:
    import pytds

    db_name = target.db_name or "test"
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


def run_oracle_sync(target: Target) -> dict[str, Any]:
    import oracledb

    from app.engines.oracle import _init_oracle_client_if_needed

    _init_oracle_client_if_needed()
    ops = 0
    warnings: list[str] = []
    dsn = f"{target.host}:{target.port}/{target.db_name or 'XE'}"
    with oracledb.connect(user=target.user, password=target.password, dsn=dsn) as conn:
        with conn.cursor() as cur:
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
