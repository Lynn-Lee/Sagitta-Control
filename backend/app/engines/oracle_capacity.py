"""Oracle 容量采集 SQL 候选。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OracleCapacityQueryCandidate:
    name: str
    sql: str
    params: dict[str, Any] | None


def oracle_table_capacity_query_candidates(owner: str) -> list[OracleCapacityQueryCandidate]:
    owner = owner.upper()
    dba_sql = """
        WITH block_size AS (
            SELECT 8192 AS bytes FROM dual
        ),
        table_stats AS (
            SELECT
                table_name,
                COALESCE(num_rows, 0) AS table_rows,
                GREATEST(
                    COALESCE(blocks, 0) * (SELECT bytes FROM block_size),
                    COALESCE(num_rows, 0) * COALESCE(avg_row_len, 0),
                    0
                ) AS estimated_data_length
            FROM dba_tables
            WHERE owner = :owner
        ),
        index_stats AS (
            SELECT
                table_name,
                SUM(COALESCE(leaf_blocks, 0) * (SELECT bytes FROM block_size)) AS estimated_index_length
            FROM dba_indexes
            WHERE table_owner = :owner
            GROUP BY table_name
        ),
        table_segments AS (
            SELECT segment_name AS table_name, SUM(bytes) AS data_length
            FROM dba_segments
            WHERE owner = :owner
              AND segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
            GROUP BY segment_name
        ),
        lob_segments AS (
            SELECT l.table_name, SUM(s.bytes) AS lob_data_length
            FROM dba_lobs l
            JOIN dba_segments s
              ON s.owner = l.owner
             AND s.segment_name = l.segment_name
            WHERE l.owner = :owner
              AND s.segment_type IN ('LOBSEGMENT', 'LOB PARTITION', 'LOB SUBPARTITION')
            GROUP BY l.table_name
        ),
        lob_index_segments AS (
            SELECT l.table_name, SUM(s.bytes) AS lob_index_length
            FROM dba_lobs l
            JOIN dba_segments s
              ON s.owner = l.owner
             AND s.segment_name = l.index_name
            WHERE l.owner = :owner
              AND s.segment_type IN ('LOBINDEX', 'LOB PARTITION', 'LOB SUBPARTITION')
            GROUP BY l.table_name
        ),
        index_segments AS (
            SELECT i.table_name, SUM(s.bytes) AS index_length
            FROM dba_indexes i
            JOIN dba_segments s
              ON s.owner = i.owner
             AND s.segment_name = i.index_name
            WHERE i.table_owner = :owner
              AND s.segment_type IN ('INDEX', 'INDEX PARTITION', 'INDEX SUBPARTITION')
            GROUP BY i.table_name
        )
        SELECT
            t.table_name,
            t.table_rows,
            COALESCE(ts.data_length, t.estimated_data_length, 0)
              + COALESCE(ls.lob_data_length, 0) AS data_length,
            COALESCE(ix.index_length, ist.estimated_index_length, 0)
              + COALESCE(lis.lob_index_length, 0) AS index_length,
            COALESCE(ts.data_length, t.estimated_data_length, 0)
              + COALESCE(ls.lob_data_length, 0)
              + COALESCE(ix.index_length, ist.estimated_index_length, 0)
              + COALESCE(lis.lob_index_length, 0) AS total_size
        FROM table_stats t
        LEFT JOIN table_segments ts ON ts.table_name = t.table_name
        LEFT JOIN lob_segments ls ON ls.table_name = t.table_name
        LEFT JOIN lob_index_segments lis ON lis.table_name = t.table_name
        LEFT JOIN index_segments ix ON ix.table_name = t.table_name
        LEFT JOIN index_stats ist ON ist.table_name = t.table_name
        ORDER BY total_size DESC, t.table_name
        """
    all_sql = dba_sql.replace("dba_tables", "all_tables").replace(
        "dba_indexes", "all_indexes"
    ).replace("dba_segments", "all_segments").replace("dba_lobs", "all_lobs")
    user_segments_sql = """
        WITH table_segments AS (
            SELECT segment_name AS table_name, SUM(bytes) AS data_length
            FROM user_segments
            WHERE segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
            GROUP BY segment_name
        ),
        lob_segments AS (
            SELECT l.table_name, SUM(s.bytes) AS lob_data_length
            FROM user_lobs l
            JOIN user_segments s
              ON s.segment_name = l.segment_name
            WHERE s.segment_type IN ('LOBSEGMENT', 'LOB PARTITION', 'LOB SUBPARTITION')
            GROUP BY l.table_name
        ),
        lob_index_segments AS (
            SELECT l.table_name, SUM(s.bytes) AS lob_index_length
            FROM user_lobs l
            JOIN user_segments s
              ON s.segment_name = l.index_name
            WHERE s.segment_type IN ('LOBINDEX', 'LOB PARTITION', 'LOB SUBPARTITION')
            GROUP BY l.table_name
        ),
        index_segments AS (
            SELECT i.table_name, SUM(s.bytes) AS index_length
            FROM user_indexes i
            JOIN user_segments s
              ON s.segment_name = i.index_name
            WHERE s.segment_type IN ('INDEX', 'INDEX PARTITION', 'INDEX SUBPARTITION')
            GROUP BY i.table_name
        )
        SELECT
            t.table_name,
            COALESCE(t.num_rows, 0) AS table_rows,
            COALESCE(
                ts.data_length,
                GREATEST(
                    COALESCE(t.blocks, 0) * 8192,
                    COALESCE(t.num_rows, 0) * COALESCE(t.avg_row_len, 0),
                    0
                ),
                0
            )
              + COALESCE(ls.lob_data_length, 0) AS data_length,
            COALESCE(ix.index_length, COALESCE(ist.estimated_index_length, 0), 0)
              + COALESCE(lis.lob_index_length, 0) AS index_length,
            COALESCE(
                ts.data_length,
                GREATEST(
                    COALESCE(t.blocks, 0) * 8192,
                    COALESCE(t.num_rows, 0) * COALESCE(t.avg_row_len, 0),
                    0
                ),
                0
            )
              + COALESCE(ls.lob_data_length, 0)
              + COALESCE(ix.index_length, COALESCE(ist.estimated_index_length, 0), 0)
              + COALESCE(lis.lob_index_length, 0) AS total_size
        FROM user_tables t
        LEFT JOIN table_segments ts ON ts.table_name = t.table_name
        LEFT JOIN lob_segments ls ON ls.table_name = t.table_name
        LEFT JOIN lob_index_segments lis ON lis.table_name = t.table_name
        LEFT JOIN index_segments ix ON ix.table_name = t.table_name
        LEFT JOIN (
            SELECT table_name, SUM(COALESCE(leaf_blocks, 0) * 8192) AS estimated_index_length
            FROM user_indexes
            GROUP BY table_name
        ) ist ON ist.table_name = t.table_name
        ORDER BY total_size DESC, t.table_name
        """
    all_metadata_sql = """
        SELECT
            t.table_name,
            COALESCE(t.num_rows, 0) AS table_rows,
            GREATEST(COALESCE(t.blocks, 0) * 8192, COALESCE(t.num_rows, 0) * COALESCE(t.avg_row_len, 0), 0) AS data_length,
            COALESCE(ix.index_length, 0) AS index_length,
            GREATEST(COALESCE(t.blocks, 0) * 8192, COALESCE(t.num_rows, 0) * COALESCE(t.avg_row_len, 0), 0)
              + COALESCE(ix.index_length, 0) AS total_size
        FROM all_tables t
        LEFT JOIN (
            SELECT table_name, SUM(COALESCE(leaf_blocks, 0) * 8192) AS index_length
            FROM all_indexes
            WHERE table_owner = :owner
            GROUP BY table_name
        ) ix ON ix.table_name = t.table_name
        WHERE t.owner = :owner
        ORDER BY total_size DESC, t.table_name
        """
    user_metadata_sql = all_metadata_sql.replace("FROM all_tables", "FROM user_tables").replace(
        "FROM all_indexes", "FROM user_indexes"
    ).replace("WHERE table_owner = :owner", "").replace("WHERE t.owner = :owner", "")
    all_legacy_sql = """
        SELECT
            t.table_name,
            COALESCE(t.num_rows, 0) AS table_rows,
            COALESCE(t.blocks, 0) * 8192 AS data_length,
            0 AS index_length,
            COALESCE(t.blocks, 0) * 8192 AS total_size
        FROM all_tables t
        WHERE t.owner = :owner
        ORDER BY total_size DESC, t.table_name
        """
    user_legacy_sql = all_legacy_sql.replace("FROM all_tables", "FROM user_tables").replace(
        "WHERE t.owner = :owner", ""
    )
    return [
        OracleCapacityQueryCandidate("dba_segments", dba_sql, {"owner": owner}),
        OracleCapacityQueryCandidate("all_segments", all_sql, {"owner": owner}),
        OracleCapacityQueryCandidate("user_segments", user_segments_sql, None),
        OracleCapacityQueryCandidate("all_metadata", all_metadata_sql, {"owner": owner}),
        OracleCapacityQueryCandidate("user_metadata", user_metadata_sql, None),
        OracleCapacityQueryCandidate("all_legacy_metadata", all_legacy_sql, {"owner": owner}),
        OracleCapacityQueryCandidate("user_legacy_metadata", user_legacy_sql, None),
    ]
