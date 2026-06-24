import json

from app.engines.registry import supported_engines
from app.services.commercial_ops import CommercialOpsService
from app.services.commercial_ops_metadata import COMMERCIAL_VERSION
from app.services.monitor import MonitorService


def test_engine_matrix_contains_required_capabilities():
    matrix = CommercialOpsService.engine_matrix()
    labels = matrix["capability_labels"]

    assert labels["connection"] == "连接测试"
    assert labels["kill_session"] == "Kill 会话"
    assert any(item["db_type"] == "mysql" and item["support_level"] == "ga" for item in matrix["items"])
    assert any(
        item["db_type"] == "pgsql" and item["label"] == "PostgreSQL" and item["support_level"] == "ga"
        for item in matrix["items"]
    )
    assert not any(item["db_type"] == "postgres" for item in matrix["items"])
    assert any(
        item["db_type"] == "cassandra" and item["support_level"] == "read_only_metadata"
        for item in matrix["items"]
    )
    for item in matrix["items"]:
        assert "2026" not in item["validation_required"]
        assert "ECS" not in item["validation_required"]
        assert "实测" not in item["validation_required"]
    assert next(item for item in matrix["items"] if item["db_type"] == "opensearch")[
        "validation_required"
    ] == "支持"
    cassandra = next(item for item in matrix["items"] if item["db_type"] == "cassandra")
    assert cassandra["validation_required"] == "只读/元数据支持；SQL 洞察、DDL/DML/BATCH 不承诺"


def test_engine_matrix_db_types_match_registered_engines():
    matrix = CommercialOpsService.engine_matrix()
    matrix_types = {item["db_type"] for item in matrix["items"]}

    registry_types = set(supported_engines()) - {"custom_db"}
    assert matrix_types == registry_types


def test_acceptance_markdown_renders_check_results():
    report = {
        "project": "Sagitta Control",
        "project_code": "sagitta-control",
        "generated_at": "2026-05-28T00:00:00+00:00",
        "generated_by": "admin",
        "status": "success",
        "readiness": {
            "conclusion": "可推广",
            "summary": "试用、授权、实例治理和验收材料已形成闭环。",
        },
        "summary": {"passed": 1, "failed": 0, "skipped": 1},
        "checks": [
            {"name": "健康检查", "ok": True, "detail": "ok"},
            {"name": "客户包签名", "ok": False, "detail": "未生成", "required": False},
            {"name": "实例链路检查", "ok": True, "detail": "跳过", "skipped": True},
        ],
    }

    markdown = CommercialOpsService.acceptance_markdown(report)

    assert "Sagitta Control 商业交付验收报告" in markdown
    assert "推广结论：可推广" in markdown
    assert "PASS" in markdown
    assert "WARN" in markdown
    assert "SKIP" in markdown


def test_delivery_preflight_requires_backup_restore_and_upgrade_scripts(tmp_path):
    result = CommercialOpsService.delivery_preflight(tmp_path)
    action_keys = {item["key"] for item in result["checks"] if item["blocking"] and not item["ok"]}

    assert result["status"] == "blocked"
    assert {"backup_script", "restore_script", "upgrade_script", "customer_go_live_scripts"}.issubset(
        action_keys
    )


def test_onboarding_step_contract_exposes_go_live_guidance():
    steps = CommercialOpsService._build_onboarding_steps(
        completed=set(),
        system_hints={
            "branding": False,
            "license": False,
            "auth": False,
            "notification": False,
            "first_instance": False,
            "governance": False,
            "acceptance": False,
        },
    )

    by_key = {item["key"]: item for item in steps}
    assert by_key["first_instance"]["required"] is True
    assert by_key["first_instance"]["status"] == "blocked"
    assert by_key["first_instance"]["evidence"] == "未检测到活跃实例"
    assert by_key["first_instance"]["action_label"] == "接入实例"
    assert by_key["first_instance"]["quick_action"] == "navigate"

    assert by_key["notification"]["required"] is False
    assert by_key["notification"]["status"] == "todo"
    assert "连通性测试" in by_key["notification"]["suggested_action"]

    assert by_key["governance"]["can_auto_fix"] is True
    assert by_key["governance"]["quick_action"] == "trial_bootstrap"
    assert by_key["acceptance"]["quick_action"] == "generate_acceptance"


def test_bundled_delivery_manifest_matches_current_commercial_version():
    manifest = CommercialOpsService._load_delivery_manifest()

    assert manifest is not None
    assert manifest["version"] == COMMERCIAL_VERSION


def test_delivery_preflight_detects_release_materials(tmp_path):
    files = [
        "deploy/backup/backup-postgres.sh",
        "deploy/backup/restore-postgres.sh",
        "deploy/customer/upgrade.sh",
        "deploy/customer/prepare-go-live-env.sh",
        "deploy/customer/go-live-check.sh",
        "scripts/validate-commercial-build-context.sh",
        "scripts/validate-commercial-images.sh",
        "scripts/generate-commercial-sbom.sh",
        "scripts/sign-commercial-artifacts.sh",
    ]
    for relative in files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        path.chmod(0o755)

    release_dir = tmp_path / "dist-commercial"
    release_dir.mkdir()
    (release_dir / f"Sagitta-Control-v{COMMERCIAL_VERSION}.zip.sha256").write_text("checksum\n", encoding="utf-8")
    (release_dir / f"Sagitta-Control-v{COMMERCIAL_VERSION}.zip.sig.json").write_text("{}", encoding="utf-8")
    sbom_dir = release_dir / "sbom"
    sbom_dir.mkdir()
    (sbom_dir / f"sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json").write_text("{}", encoding="utf-8")
    (sbom_dir / f"sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json.sha256").write_text("checksum\n", encoding="utf-8")
    (sbom_dir / f"sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json.bundle").write_text("{}", encoding="utf-8")

    result = CommercialOpsService.delivery_preflight(tmp_path)

    assert result["status"] == "ready"
    assert all(item["ok"] for item in result["checks"])


def test_delivery_preflight_can_use_release_manifest(tmp_path):
    manifest = {
        "version": COMMERCIAL_VERSION,
        "materials": [
            {"path": "deploy/backup/backup-postgres.sh", "executable": True},
            {"path": "deploy/backup/restore-postgres.sh", "executable": True},
            {"path": "deploy/customer/upgrade.sh", "executable": True},
            {"path": "deploy/customer/prepare-go-live-env.sh", "executable": True},
            {"path": "deploy/customer/go-live-check.sh", "executable": True},
            {"path": "scripts/validate-commercial-build-context.sh", "executable": True},
            {"path": "scripts/validate-commercial-images.sh", "executable": True},
            {"path": "scripts/generate-commercial-sbom.sh", "executable": True},
            {"path": "scripts/sign-commercial-artifacts.sh", "executable": True},
            {"path": f"dist-commercial/Sagitta-Control-v{COMMERCIAL_VERSION}.zip.sha256", "executable": False},
            {"path": f"dist-commercial/Sagitta-Control-v{COMMERCIAL_VERSION}.zip.sig.json", "executable": False},
            {"path": f"dist-commercial/sbom/sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json", "executable": False},
            {"path": f"dist-commercial/sbom/sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json.sha256", "executable": False},
            {"path": f"dist-commercial/sbom/sagitta-control-backend-{COMMERCIAL_VERSION}.cyclonedx.json.bundle", "executable": False},
        ],
    }

    result = CommercialOpsService.delivery_preflight(tmp_path, manifest=manifest)

    assert result["status"] == "ready"
    assert all(item["ok"] for item in result["checks"])
    assert "发布清单" in result["checks"][0]["detail"]


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
