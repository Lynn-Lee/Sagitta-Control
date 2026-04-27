from datetime import date, timedelta

from app.services.risk_plan import RiskPlanService


def test_workflow_delete_without_where_is_high_risk():
    plan = RiskPlanService.build_workflow_plan("mysql", "app", "DELETE FROM users")

    assert plan.level == "high"
    assert plan.requires_manual_remark is True
    assert any("WHERE" in item for item in plan.risks)


def test_workflow_update_with_where_is_medium_risk():
    plan = RiskPlanService.build_workflow_plan(
        "pgsql",
        "app",
        "UPDATE users SET status = 0 WHERE id = 1",
    )

    assert plan.level == "medium"
    assert plan.requires_manual_remark is False
    assert any("备份" in item for item in plan.suggestions)


def test_workflow_select_is_low_risk():
    plan = RiskPlanService.build_workflow_plan("mysql", "app", "SELECT * FROM users LIMIT 10")

    assert plan.level == "low"
    assert plan.requires_confirmation is False


def test_workflow_ddl_is_high_risk():
    plan = RiskPlanService.build_workflow_plan("mysql", "app", "TRUNCATE TABLE users")

    assert plan.level == "high"
    assert plan.requires_confirmation is True
    assert any("DDL" in item for item in plan.risks)


def test_workflow_delete_without_where_requires_high_risk_submit_permission():
    assert RiskPlanService.is_privileged_workflow_sql("mysql", "DELETE FROM users") is True


def test_workflow_update_with_where_does_not_require_high_risk_submit_permission():
    assert (
        RiskPlanService.is_privileged_workflow_sql(
            "mysql",
            "UPDATE users SET status = 0 WHERE id = 1",
        )
        is False
    )


def test_workflow_insert_select_is_medium_risk():
    plan = RiskPlanService.build_workflow_plan(
        "mysql",
        "app",
        "INSERT INTO audit_users SELECT * FROM users WHERE status = 0",
    )

    assert plan.level == "medium"
    assert plan.requires_confirmation is False
    assert any("INSERT ... SELECT" in item for item in plan.risks)


def test_query_privilege_instance_long_term_is_high_risk():
    plan = RiskPlanService.build_query_privilege_plan(
        db_type="mysql",
        scope_type="instance",
        db_name="",
        table_name="",
        valid_date=date.today() + timedelta(days=180),
        limit_num=100,
    )

    assert plan.level == "high"
    assert plan.requires_manual_remark is True


def test_query_privilege_database_scope_is_high_risk():
    plan = RiskPlanService.build_query_privilege_plan(
        db_type="mysql",
        scope_type="database",
        db_name="ump_testdb",
        table_name="",
        valid_date=date.today() + timedelta(days=7),
        limit_num=1000,
    )

    assert plan.level == "high"
    assert plan.requires_manual_remark is True
    assert "全部表" in " ".join(plan.risks)


def test_query_privilege_table_short_term_is_low_risk():
    plan = RiskPlanService.build_query_privilege_plan(
        db_type="mysql",
        scope_type="table",
        db_name="ump_testdb",
        table_name="orders",
        valid_date=date.today() + timedelta(days=7),
        limit_num=1000,
    )

    assert plan.level == "low"
    assert plan.requires_manual_remark is False


def test_query_privilege_table_medium_by_duration_and_limit():
    plan = RiskPlanService.build_query_privilege_plan(
        db_type="mysql",
        scope_type="table",
        db_name="ump_testdb",
        table_name="orders",
        valid_date=date.today() + timedelta(days=45),
        limit_num=10000,
    )

    assert plan.level == "medium"
    assert plan.requires_confirmation is False


def test_archive_purge_is_high_risk():
    plan = RiskPlanService.build_archive_plan(
        db_type="oracle",
        archive_mode="purge",
        source_db="app",
        source_table="orders",
        condition="created_at < DATE '2024-01-01'",
        batch_size=1000,
        estimated_rows=500,
    )

    assert plan.level == "high"
    assert plan.requires_manual_remark is True
    assert any("备份" in item for item in plan.suggestions)


def test_archive_dest_zero_rows_is_low_risk():
    plan = RiskPlanService.build_archive_plan(
        db_type="mysql",
        archive_mode="dest",
        source_db="app",
        source_table="orders",
        condition="created_at < '2024-01-01'",
        batch_size=1000,
        estimated_rows=0,
        dest_db="archive",
        dest_table="orders",
    )

    assert plan.level == "low"
    assert plan.requires_manual_remark is False


def test_archive_dest_with_rows_is_medium_risk():
    plan = RiskPlanService.build_archive_plan(
        db_type="mysql",
        archive_mode="dest",
        source_db="app",
        source_table="orders",
        condition="created_at < '2024-01-01'",
        batch_size=1000,
        estimated_rows=500,
        dest_db="archive",
        dest_table="orders",
    )

    assert plan.level == "medium"
    assert plan.requires_confirmation is False


def test_archive_unknown_estimate_is_high_risk():
    plan = RiskPlanService.build_archive_plan(
        db_type="mysql",
        archive_mode="dest",
        source_db="app",
        source_table="orders",
        condition="created_at < '2024-01-01'",
        batch_size=1000,
        estimated_rows=None,
        dest_db="archive",
        dest_table="orders",
    )

    assert plan.level == "high"
    assert plan.requires_manual_remark is True


def test_non_relational_returns_unsupported_low_risk_plan():
    plan = RiskPlanService.build_workflow_plan("mongo", "app", "db.users.find({})")

    assert plan.level == "low"
    assert plan.requires_manual_remark is False
    assert "不支持" in plan.summary
