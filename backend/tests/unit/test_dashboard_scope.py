from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.models.instance import Instance, InstanceDatabase
from app.services.dashboard import DashboardService, _row_int, _row_value


class FakeScalars:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    def all(self) -> list[int]:
        return self._values


class FakeResult:
    def __init__(
        self,
        *,
        scalar_value: int | None = None,
        rows: list[Any] | None = None,
        scalar_values: list[int] | None = None,
        one_value: Any | None = None,
    ) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []
        self._scalar_values = scalar_values or []
        self._one_value = one_value

    def scalar(self) -> int | None:
        return self._scalar_value

    def one(self) -> Any:
        if self._one_value is not None:
            return self._one_value
        return self._rows[0]

    def all(self) -> list[Any]:
        return self._rows

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._scalar_values)


class FakeDB:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        return self.results.pop(0)


class FakeRow:
    def __init__(self, **values: Any) -> None:
        self._mapping = values
        for key, value in values.items():
            setattr(self, key, value)


def sql_text(stmt: Any) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_row_helpers_read_mapping_defaults() -> None:
    row = FakeRow(count="7", nullable=None)

    assert _row_value(row, "count") == "7"
    assert _row_value(row, "missing", default="fallback") == "fallback"
    assert _row_int(row, "count") == 7
    assert _row_int(row, "nullable") == 0
    assert _row_int(row, "missing") == 0


@pytest.mark.asyncio
async def test_resolve_instance_scope_for_global_user_skips_db() -> None:
    db = FakeDB([])

    scope = await DashboardService._resolve_instance_scope(
        db,  # type: ignore[arg-type]
        {"is_superuser": True, "role": "engineer"},
    )

    assert scope == {"mode": "global", "label": "全量资源", "instance_ids": None}
    assert db.statements == []


@pytest.mark.asyncio
async def test_resolve_instance_scope_without_resource_groups_is_empty() -> None:
    db = FakeDB([])

    scope = await DashboardService._resolve_instance_scope(
        db,  # type: ignore[arg-type]
        {"is_superuser": False, "role": "engineer", "resource_groups": []},
    )

    assert scope == {"mode": "instance_scope", "label": "可见资源范围", "instance_ids": []}
    assert db.statements == []


@pytest.mark.asyncio
async def test_resolve_instance_scope_loads_visible_instance_ids() -> None:
    db = FakeDB([FakeResult(scalar_values=[3, 5])])

    scope = await DashboardService._resolve_instance_scope(
        db,  # type: ignore[arg-type]
        {"is_superuser": False, "role": "engineer", "resource_groups": [10, 20]},
    )

    assert scope == {"mode": "instance_scope", "label": "可见资源范围", "instance_ids": [3, 5]}
    assert len(db.statements) == 1


def test_apply_instance_scope_filters_empty_and_visible_ids() -> None:
    empty_sql = sql_text(
        DashboardService._apply_instance_scope(
            select(Instance), {"mode": "instance_scope", "instance_ids": []}
        )
    )
    scoped_sql = sql_text(
        DashboardService._apply_instance_scope(
            select(Instance), {"mode": "instance_scope", "instance_ids": [1, 2]}
        )
    )
    global_sql = sql_text(
        DashboardService._apply_instance_scope(select(Instance), {"mode": "global"})
    )

    assert "sql_instance.id = -1" in empty_sql
    assert "sql_instance.id IN (1, 2)" in scoped_sql
    assert "WHERE" not in global_sql


def test_apply_instance_database_scope_filters_empty_and_visible_ids() -> None:
    empty_sql = sql_text(
        DashboardService._apply_instance_database_scope(
            select(InstanceDatabase), {"mode": "instance_scope", "instance_ids": []}
        )
    )
    scoped_sql = sql_text(
        DashboardService._apply_instance_database_scope(
            select(InstanceDatabase), {"mode": "instance_scope", "instance_ids": [1, 2]}
        )
    )
    global_sql = sql_text(
        DashboardService._apply_instance_database_scope(
            select(InstanceDatabase), {"mode": "global"}
        )
    )

    assert "instance_database.instance_id = -1" in empty_sql
    assert "instance_database.instance_id IN (1, 2)" in scoped_sql
    assert "WHERE" not in global_sql


@pytest.mark.asyncio
async def test_get_instance_overview_returns_card_and_distribution_counts() -> None:
    db = FakeDB(
        [
            FakeResult(scalar_value=4),
            FakeResult(scalar_value=12),
            FakeResult(scalar_value=9),
            FakeResult(scalar_value=3),
            FakeResult(rows=[FakeRow(db_type="mysql", count="3"), FakeRow(db_type="pgsql", count=1)]),
            FakeResult(scalar_value=3),
            FakeResult(scalar_value=1),
        ]
    )

    result = await DashboardService.get_instance_overview(
        db,  # type: ignore[arg-type]
        {"is_superuser": True, "role": "superadmin"},
    )

    assert result["scope"] == {"mode": "global", "label": "全量资源"}
    assert result["cards"] == {
        "visible_instance_count": 4,
        "synced_database_count": 12,
        "enabled_database_count": 9,
        "disabled_database_count": 3,
    }
    assert result["instance_type_distribution"] == [
        {"db_type": "mysql", "count": 3},
        {"db_type": "pgsql", "count": 1},
    ]
    assert result["instance_status_distribution"] == [
        {"label": "已启用实例", "count": 3},
        {"label": "已禁用实例", "count": 1},
    ]
    assert result["database_status_distribution"] == [
        {"label": "已启用库/Schema", "count": 9},
        {"label": "已禁用库/Schema", "count": 3},
    ]
    assert len(db.statements) == 7


@pytest.mark.asyncio
async def test_get_query_overview_returns_cards_trend_and_top_users() -> None:
    db = FakeDB(
        [
            FakeResult(scalar_value=20),
            FakeResult(scalar_value=4),
            FakeResult(scalar_value=6),
            FakeResult(scalar_value=2),
            FakeResult(scalar_value=1),
            FakeResult(scalar_value=8),
            FakeResult(scalar_value=5),
            FakeResult(scalar_value=3),
            FakeResult(rows=[FakeRow(d="2099-01-01", query_count=7, query_user_count=2)]),
            FakeResult(rows=[FakeRow(d="2099-01-01", failure_count=1)]),
            FakeResult(rows=[FakeRow(d="2099-01-01", masked_count=4)]),
            FakeResult(rows=[FakeRow(d="2099-01-01", approved_count=3)]),
            FakeResult(rows=[FakeRow(d="2099-01-01", rejected_count=2)]),
            FakeResult(rows=[FakeRow(d="2099-01-01", revoked_count=1)]),
            FakeResult(scalar_value=11),
            FakeResult(scalar_value=12),
            FakeResult(rows=[FakeRow(user_id=7, query_count=9), FakeRow(user_id=None, query_count=99)]),
            FakeResult(rows=[(7, "", "alice")]),
        ]
    )

    result = await DashboardService.get_query_overview(
        db,  # type: ignore[arg-type]
        {"is_superuser": True, "role": "superadmin"},
        days=2,
    )

    assert result["scope"] == {"mode": "global", "label": "全量数据"}
    assert result["cards"] == {
        "period_query_count": 20,
        "period_query_user_count": 4,
        "period_failure_count": 3,
        "period_masked_count": 6,
        "pending_query_priv_apply_count": 5,
        "approved_query_priv_apply_count": 8,
        "rejected_query_priv_apply_count": 1,
        "revoked_query_privilege_count": 3,
    }
    assert result["trend"]["range_label"] == "最近2天"
    assert len(result["trend"]["dates"]) == 2
    assert result["trend"]["pending_stock_count"] == [11, 12]
    assert result["top_users"] == [{"display_name": "alice", "query_count": 9}]
    assert len(db.statements) == 18


@pytest.mark.asyncio
async def test_get_archive_overview_returns_cards_trends_and_rankings() -> None:
    db = FakeDB(
        [
            FakeResult(scalar_value=30),
            FakeResult(scalar_value=12),
            FakeResult(scalar_value=2),
            FakeResult(scalar_value=1),
            FakeResult(scalar_value=4),
            FakeResult(scalar_value=5),
            FakeResult(scalar_value=6),
            FakeResult(scalar_value=7),
            FakeResult(scalar_value=8),
            FakeResult(scalar_value=9),
            FakeResult(one_value=(1000, 600)),
            FakeResult(rows=[FakeRow(d="2099-01-01", submit_count=3, estimated_rows=300)]),
            FakeResult(
                rows=[
                    FakeRow(
                        d="2099-01-01",
                        success_count=2,
                        failed_count=1,
                        canceled_count=0,
                        processed_rows=200,
                    )
                ]
            ),
            FakeResult(scalar_value=13),
            FakeResult(scalar_value=14),
            FakeResult(rows=[FakeRow(created_by_id=7, count=4, estimated_rows=400)]),
            FakeResult(rows=[(7, "归档工程师", "archiver")]),
            FakeResult(rows=[FakeRow(instance_name="prod-mysql", count=5, estimated_rows=500)]),
            FakeResult(
                rows=[
                    FakeRow(
                        source_db="sales",
                        source_table="orders",
                        count=6,
                        estimated_rows=600,
                        processed_rows=360,
                    )
                ]
            ),
        ]
    )

    result = await DashboardService.get_archive_overview(
        db,  # type: ignore[arg-type]
        {"permissions": ["archive_review"], "id": 7},
        days=2,
    )

    assert result["scope"] == {"mode": "archive", "label": "归档任务可见范围"}
    assert result["cards"] == {
        "period_submit_count": 30,
        "pending_count": 4,
        "approved_count": 5,
        "scheduled_count": 6,
        "running_count": 7,
        "paused_count": 8,
        "success_count": 12,
        "failed_count": 2,
        "canceled_count": 1,
        "estimated_rows": 1000,
        "processed_rows": 600,
        "high_risk_active_count": 9,
    }
    assert len(result["trend"]["dates"]) == 2
    assert result["trend"]["active_stock_count"] == [13, 14]
    assert result["top_submitters"] == [
        {"display_name": "归档工程师", "count": 4, "estimated_rows": 400}
    ]
    assert result["top_instances"] == [
        {"instance_name": "prod-mysql", "count": 5, "estimated_rows": 500}
    ]
    assert result["top_tables"] == [
        {
            "source_label": "sales.orders",
            "count": 6,
            "estimated_rows": 600,
            "processed_rows": 360,
        }
    ]
    assert len(db.statements) == 19


@pytest.mark.asyncio
async def test_archive_conditions_short_circuits_for_review_permissions() -> None:
    conditions = await DashboardService._archive_conditions_for_user(
        object(),  # type: ignore[arg-type]
        {"permissions": ["archive_review"], "id": 7},
    )

    assert conditions == []


@pytest.mark.asyncio
async def test_archive_conditions_include_creator_and_visible_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def visible_ids(db: Any, user: dict[str, Any]) -> set[int]:
        return {10, 20}

    monkeypatch.setattr(DashboardService, "_visible_archive_workflow_ids_for_user", visible_ids)

    conditions = await DashboardService._archive_conditions_for_user(
        object(),  # type: ignore[arg-type]
        {"permissions": [], "id": 7},
    )

    assert len(conditions) == 1
    condition_sql = str(conditions[0].compile(compile_kwargs={"literal_binds": True}))
    assert "archive_job.created_by_id = 7" in condition_sql
    assert "archive_job.workflow_id IN (10, 20)" in condition_sql
