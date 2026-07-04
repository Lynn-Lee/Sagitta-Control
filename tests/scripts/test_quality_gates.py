from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_ci_enforces_higher_unit_coverage_threshold():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(r"--cov-fail-under=(\d+)", ci)

    assert match is not None
    assert int(match.group(1)) >= 45


def test_backend_mypy_baseline_covers_split_quality_modules():
    targets = set((ROOT / "backend" / "mypy-baseline.txt").read_text(encoding="utf-8").splitlines())

    assert "app/engines/oracle_capacity.py" in targets
    assert "app/services/commercial_readiness.py" in targets
    assert "app/services/dashboard_metrics.py" in targets


def test_large_module_split_has_dedicated_helpers():
    assert (ROOT / "backend" / "app" / "engines" / "oracle_capacity.py").exists()
    assert (ROOT / "backend" / "app" / "services" / "commercial_readiness.py").exists()
    assert (ROOT / "backend" / "app" / "services" / "dashboard_metrics.py").exists()


def test_helm_chart_rejects_known_production_default_secrets():
    schema_path = ROOT / "deploy" / "helm" / "sagitta-control" / "values.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    encoded = json.dumps(schema, ensure_ascii=False)

    for weak_value in (
        "CHANGE_ME_USE_RANDOM_32_CHARS_IN_PRODUCTION",
        "sagitta123",
        "redis123",
        "CHANGE_ME",
    ):
        assert weak_value in encoded
