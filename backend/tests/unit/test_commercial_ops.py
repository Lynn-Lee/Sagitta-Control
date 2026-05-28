import json

from app.services.commercial_ops import CommercialOpsService
from app.services.monitor import MonitorService


def test_engine_matrix_contains_required_capabilities():
    matrix = CommercialOpsService.engine_matrix()
    labels = matrix["capability_labels"]

    assert labels["connection"] == "连接测试"
    assert labels["kill_session"] == "Kill 会话"
    assert any(item["db_type"] == "mysql" and item["support_level"] == "ga" for item in matrix["items"])
    assert any(item["support_level"] == "read_only_metadata" for item in matrix["items"])


def test_acceptance_markdown_renders_check_results():
    report = {
        "project": "SagittaDB",
        "project_code": "sagittadb",
        "generated_at": "2026-05-28T00:00:00+00:00",
        "generated_by": "admin",
        "status": "success",
        "summary": {"passed": 1, "failed": 0, "skipped": 1},
        "checks": [
            {"name": "健康检查", "ok": True, "detail": "ok"},
            {"name": "实例链路检查", "ok": True, "detail": "跳过", "skipped": True},
        ],
    }

    markdown = CommercialOpsService.acceptance_markdown(report)

    assert "SagittaDB 商业交付验收报告" in markdown
    assert "PASS" in markdown
    assert "SKIP" in markdown


def test_build_rows_file_json_export():
    content, media_type, filename = CommercialOpsService.build_rows_file(
        [{"username": "admin", "action": "activate_license"}],
        "json",
        "audit_logs",
    )

    assert media_type == "application/json; charset=utf-8"
    assert filename == "audit_logs.json"
    assert json.loads(content.decode("utf-8"))[0]["action"] == "activate_license"


def test_alert_comparison_supports_default_operator():
    assert MonitorService._compare_alert_value(0.9, ">=", 0.8)
    assert MonitorService._compare_alert_value(2, ">", 1)
    assert not MonitorService._compare_alert_value(0, ">", 0)
