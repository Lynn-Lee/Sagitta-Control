from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_ga_print_results_keeps_skip_out_of_pass_count(capsys):
    ga = load_script("ga_acceptance_check_test", "ga-acceptance-check.py")

    exit_code = ga.print_results(
        [
            ga.CheckResult("后端健康检查", True, "HTTP 200", domain="baseline"),
            ga.CheckResult(
                "数据字典列元数据",
                True,
                "未提供 --table-name",
                skipped=True,
                domain="dictionary",
                promised=False,
            ),
        ]
    )

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "1 通过，1 跳过，0 失败" in captured
    assert "[NOT-PROMISED] 数据字典列元数据" in captured
    assert "数据字典:" in captured


def test_customer_validation_defaults_do_not_trigger_collect():
    customer = load_script("customer_engine_validation_test", "customer-engine-validation.py")
    calls: list[tuple[str, str, object]] = []

    class FakeClient:
        def request(self, method: str, path: str, body=None):
            calls.append((method, path, body))
            if path == "/api/v1/instances/1/":
                return 200, {"db_type": "elasticsearch"}
            return 200, {}

    args = SimpleNamespace(
        sync_databases=False,
        execute_readonly_query=False,
        submit_workflow_boundary=False,
        collect_sql_activity=False,
        limit_num=100,
        group_id=None,
        flow_id=None,
    )
    target = customer.Target(
        db_type="elasticsearch",
        instance_id=1,
        db_name="analytics",
        table_name="orders",
        read_sql="SELECT * FROM orders LIMIT 1",
    )
    results = []

    customer.validate_target(FakeClient(), target, args, results)

    paths = [path for _method, path, _body in calls]
    assert not any("/api/v1/slowlog/collect/" in path for path in paths)
    assert any("/api/v1/slowlog/overview/" in path for path in paths)
    assert any("/api/v1/slowlog/logs/" in path for path in paths)
    collect_skip = next(result for result in results if result.name == "手动触发 SQL 活动采集")
    assert collect_skip.skipped is True
    assert collect_skip.promised is False

    matrix = customer.summarize_matrix(results)
    domains = {(row["domain"], row["promised"]) for row in matrix}
    assert ("workflow", True) in domains
    assert ("query", True) in domains
    assert ("observability", True) in domains
    assert ("operations", True) in domains
    assert ("dictionary", True) in domains


def test_customer_validation_rejects_unknown_promised_domain():
    customer = load_script("customer_engine_validation_domain_test", "customer-engine-validation.py")

    try:
        customer.normalize_promised_domains(["query", "unknown"])
    except ValueError as exc:
        assert "未知 promised_domains" in str(exc)
    else:
        raise AssertionError("unknown promised domain should fail")
