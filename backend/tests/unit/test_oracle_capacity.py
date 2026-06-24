from __future__ import annotations

from app.engines.oracle_capacity import oracle_table_capacity_query_candidates


def test_oracle_capacity_candidates_prefer_privileged_then_user_fallbacks():
    candidates = oracle_table_capacity_query_candidates("demo")

    assert [item.name for item in candidates] == [
        "dba_segments",
        "all_segments",
        "user_segments",
        "all_metadata",
        "user_metadata",
        "all_legacy_metadata",
        "user_legacy_metadata",
    ]
    assert candidates[0].params == {"owner": "DEMO"}
    assert candidates[2].params is None
    assert "FROM dba_tables" in candidates[0].sql
    assert "FROM user_tables" in candidates[-1].sql
