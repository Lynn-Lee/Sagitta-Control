#!/usr/bin/env python3
"""客户同构环境引擎验证脚本。

脚本只通过 HTTP API 访问已部署的 Sagitta Control 环境，便于实施人员在客户现场
或内部验证环境生成可归档的 JSON/Markdown 记录。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SUPPORTED_ENGINE_TYPES = {"oracle", "mssql", "elasticsearch", "opensearch", "doris"}
DOMAIN_LABELS = {
    "workflow": "SQL 工单",
    "query": "在线查询",
    "observability": "观测中心",
    "operations": "运维工具",
    "dictionary": "数据字典",
}
DEFAULT_PROMISED_DOMAINS = tuple(DOMAIN_LABELS.keys())


@dataclass
class Target:
    db_type: str
    instance_id: int
    db_name: str
    table_name: str = ""
    read_sql: str = "SELECT 1"
    expected_query_status: list[int] = field(default_factory=lambda: [200, 403])
    run_query: bool = False
    run_mutating_workflow_check: bool = False
    support_level: str = "validated_minimal"
    promised_domains: list[str] = field(default_factory=lambda: list(DEFAULT_PROMISED_DOMAINS))


@dataclass
class CheckResult:
    target: str
    name: str
    ok: bool
    detail: str
    skipped: bool = False
    domain: str = "operations"
    promised: bool = True


class ApiClient:
    def __init__(self, base_url: str, token: str = "", timeout: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return exc.code, parsed


def normalize_promised_domains(raw: Any | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_PROMISED_DOMAINS)
    if isinstance(raw, str):
        items = [item.strip() for item in raw.split(",")]
    else:
        items = [str(item).strip() for item in raw]
    domains = [item for item in items if item]
    unknown = sorted(set(domains) - set(DOMAIN_LABELS))
    if unknown:
        raise ValueError(f"未知 promised_domains: {unknown}")
    return domains


def parse_target(raw: str) -> Target:
    parts = raw.split("|", 4)
    if len(parts) < 3:
        raise ValueError(
            "--target 格式为 db_type|instance_id|db_name|table_name|read_sql；"
            "table_name/read_sql 可留空"
        )
    db_type = parts[0].strip().lower()
    if db_type not in SUPPORTED_ENGINE_TYPES:
        raise ValueError(f"不支持的客户验证后交付引擎: {db_type}")
    return Target(
        db_type=db_type,
        instance_id=int(parts[1]),
        db_name=parts[2].strip(),
        table_name=parts[3].strip() if len(parts) > 3 else "",
        read_sql=parts[4].strip() if len(parts) > 4 and parts[4].strip() else "SELECT 1",
    )


def load_targets(args: argparse.Namespace) -> list[Target]:
    targets = [parse_target(raw) for raw in args.target]
    if args.target_file:
        data = json.loads(Path(args.target_file).read_text(encoding="utf-8"))
        for item in data.get("targets", data if isinstance(data, list) else []):
            db_type = str(item["db_type"]).lower()
            if db_type not in SUPPORTED_ENGINE_TYPES:
                raise ValueError(f"不支持的客户验证后交付引擎: {db_type}")
            targets.append(
                Target(
                    db_type=db_type,
                    instance_id=int(item["instance_id"]),
                    db_name=str(item.get("db_name") or ""),
                    table_name=str(item.get("table_name") or ""),
                    read_sql=str(item.get("read_sql") or "SELECT 1"),
                    expected_query_status=list(item.get("expected_query_status") or [200, 403]),
                    run_query=bool(item.get("run_query", False)),
                    run_mutating_workflow_check=bool(item.get("run_mutating_workflow_check", False)),
                    support_level=str(item.get("support_level") or "validated_minimal"),
                    promised_domains=normalize_promised_domains(item.get("promised_domains")),
                )
            )
    if not targets:
        raise ValueError("至少提供一个 --target 或 --target-file")
    return targets


def login(client: ApiClient, username: str, password: str) -> str:
    status, payload = client.request(
        "POST", "/api/v1/auth/login/", {"username": username, "password": password}
    )
    if status != 200:
        raise RuntimeError(f"登录失败 HTTP {status}: {payload}")
    if payload.get("password_change_required"):
        raise RuntimeError("账号需要先修改密码")
    if payload.get("requires_2fa"):
        raise RuntimeError("账号启用了 2FA，请改用 --token")
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("登录响应缺少 access_token")
    return str(token)


def run_check(
    results: list[CheckResult],
    client: ApiClient,
    target: Target,
    name: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    expected: set[int] | None = None,
    *,
    domain: str = "operations",
    promised: bool | None = None,
) -> Any:
    expected = expected or {200}
    label = f"{target.db_type}#{target.instance_id}"
    is_promised = domain in target.promised_domains if promised is None else promised
    try:
        status, payload = client.request(method, path, body)
    except Exception as exc:  # noqa: BLE001 - validation should collect all failures
        results.append(
            CheckResult(
                label,
                name,
                False,
                f"请求失败：{exc}",
                domain=domain,
                promised=is_promised,
            )
        )
        return None
    if status in expected:
        results.append(
            CheckResult(label, name, True, f"HTTP {status}", domain=domain, promised=is_promised)
        )
    else:
        results.append(
            CheckResult(
                label,
                name,
                False,
                f"HTTP {status}: {payload}",
                domain=domain,
                promised=is_promised,
            )
        )
    return payload


def add_skip(
    results: list[CheckResult],
    target: Target,
    name: str,
    reason: str,
    *,
    domain: str = "operations",
    promised: bool | None = None,
) -> None:
    is_promised = domain in target.promised_domains if promised is None else promised
    results.append(
        CheckResult(
            f"{target.db_type}#{target.instance_id}",
            name,
            True,
            reason,
            skipped=True,
            domain=domain,
            promised=is_promised,
        )
    )


def validate_target(
    client: ApiClient,
    target: Target,
    args: argparse.Namespace,
    results: list[CheckResult],
) -> None:
    encoded_db = urllib.parse.quote(target.db_name)
    encoded_table = urllib.parse.quote(target.table_name)

    detail = run_check(
        results,
        client,
        target,
        "实例详情",
        "GET",
        f"/api/v1/instances/{target.instance_id}/",
        domain="operations",
    )
    if isinstance(detail, dict):
        actual_type = str(detail.get("db_type") or detail.get("data", {}).get("db_type") or "").lower()
        if actual_type and actual_type != target.db_type:
            results.append(
                CheckResult(
                    f"{target.db_type}#{target.instance_id}",
                    "实例类型匹配",
                    False,
                    f"目标声明 {target.db_type}，接口返回 {actual_type}",
                    domain="operations",
                )
            )
        else:
            results.append(
                CheckResult(
                    f"{target.db_type}#{target.instance_id}",
                    "实例类型匹配",
                    True,
                    actual_type or "接口未返回 db_type，已记录为需人工核对",
                    domain="operations",
                )
            )

    run_check(
        results,
        client,
        target,
        "连接测试",
        "POST",
        f"/api/v1/instances/{target.instance_id}/test/",
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "引擎支持矩阵",
        "GET",
        "/api/v1/system/support/engine-matrix",
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "License 状态",
        "GET",
        "/api/v1/system/license/status",
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "实施交付向导状态",
        "GET",
        "/api/v1/system/onboarding/status",
        expected={200, 403},
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "操作审计日志",
        "GET",
        "/api/v1/system/audit-logs/?page=1&page_size=1",
        expected={200, 403},
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "实例参数列表",
        "GET",
        f"/api/v1/instances/{target.instance_id}/params/",
        expected={200, 400, 403},
        domain="operations",
    )
    run_check(
        results,
        client,
        target,
        "数据库注册列表",
        "GET",
        f"/api/v1/instances/{target.instance_id}/db-list/?page=1&page_size=50",
        domain="dictionary",
    )
    if args.sync_databases:
        run_check(
            results,
            client,
            target,
            "从引擎同步库列表",
            "POST",
            f"/api/v1/instances/{target.instance_id}/db-list/sync/",
            domain="dictionary",
            promised=True,
        )
    else:
        add_skip(
            results,
            target,
            "从引擎同步库列表",
            "未开启 --sync-databases",
            domain="dictionary",
            promised=False,
        )

    run_check(
        results,
        client,
        target,
        "数据字典库列表",
        "GET",
        f"/api/v1/instances/{target.instance_id}/databases/",
        domain="dictionary",
    )
    run_check(
        results,
        client,
        target,
        "表列表",
        "GET",
        f"/api/v1/instances/{target.instance_id}/tables/?db_name={encoded_db}",
        domain="dictionary",
    )
    if target.table_name:
        run_check(
            results,
            client,
            target,
            "列元数据",
            "GET",
            f"/api/v1/instances/{target.instance_id}/columns/?db_name={encoded_db}&tb_name={encoded_table}",
            domain="dictionary",
        )
        run_check(
            results,
            client,
            target,
            "表 DDL/Mapping",
            "GET",
            f"/api/v1/instances/{target.instance_id}/ddl/?db_name={encoded_db}&tb_name={encoded_table}",
            expected={200, 400},
            domain="dictionary",
        )
        run_check(
            results,
            client,
            target,
            "约束元数据",
            "GET",
            f"/api/v1/instances/{target.instance_id}/constraints/?db_name={encoded_db}&tb_name={encoded_table}",
            expected={200, 400},
            domain="dictionary",
        )
        run_check(
            results,
            client,
            target,
            "索引元数据",
            "GET",
            f"/api/v1/instances/{target.instance_id}/indexes/?db_name={encoded_db}&tb_name={encoded_table}",
            expected={200, 400},
            domain="dictionary",
        )
    else:
        add_skip(results, target, "表级元数据", "未提供 table_name", domain="dictionary")

    query_body = {
        "instance_id": target.instance_id,
        "db_name": target.db_name,
        "sql": target.read_sql,
        "limit_num": args.limit_num,
    }
    run_check(
        results,
        client,
        target,
        "在线查询权限排查",
        "POST",
        "/api/v1/query/access-check/",
        query_body,
        expected=set(target.expected_query_status),
        domain="query",
    )
    if args.execute_readonly_query or target.run_query:
        run_check(
            results,
            client,
            target,
            "只读在线查询执行",
            "POST",
            "/api/v1/query/",
            query_body,
            expected=set(target.expected_query_status),
            domain="query",
            promised=True,
        )
    else:
        add_skip(
            results,
            target,
            "只读在线查询执行",
            "未开启 --execute-readonly-query",
            domain="query",
            promised=False,
        )

    run_check(
        results,
        client,
        target,
        "SQL 工单风险预案",
        "POST",
        "/api/v1/workflow/risk-plan/",
        {
            "instance_id": target.instance_id,
            "db_name": target.db_name,
            "sql_content": target.read_sql,
        },
        domain="workflow",
    )
    if args.submit_workflow_boundary or target.run_mutating_workflow_check:
        run_check(
            results,
            client,
            target,
            "SQL 工单审核边界",
            "POST",
            "/api/v1/workflow/",
            {
                "workflow_name": f"客户验证后交付引擎边界验证-{target.db_type}",
                "group_id": args.group_id,
                "flow_id": args.flow_id,
                "instance_id": target.instance_id,
                "db_name": target.db_name,
                "sql_content": target.read_sql,
                "is_backup": False,
                "risk_remark": "客户同构环境验证，可按验收记录清理",
            },
            expected={200, 400, 403},
            domain="workflow",
            promised=True,
        )
    else:
        add_skip(
            results,
            target,
            "SQL 工单审核边界",
            "未开启 --submit-workflow-boundary",
            domain="workflow",
            promised=False,
        )

    run_check(
        results,
        client,
        target,
        "基础指标采集",
        "GET",
        f"/api/v1/monitor/instances/{target.instance_id}/metrics/",
        expected={200, 400, 403},
        domain="observability",
    )
    run_check(
        results,
        client,
        target,
        "观测中心实例健康评分",
        "GET",
        f"/api/v1/monitor/native/instances/{target.instance_id}/health/",
        expected={200, 400, 403},
        domain="observability",
    )
    run_check(
        results,
        client,
        target,
        "SQL 洞察总览",
        "GET",
        f"/api/v1/slowlog/overview/?instance_id={target.instance_id}",
        expected={200, 403},
        domain="observability",
    )
    run_check(
        results,
        client,
        target,
        "SQL 洞察样本列表",
        "GET",
        f"/api/v1/slowlog/logs/?instance_id={target.instance_id}&page=1&page_size=1",
        expected={200, 403},
        domain="observability",
    )
    if target.db_type in {"oracle", "mssql", "doris"}:
        run_check(
            results,
            client,
            target,
            "会话/活动采集",
            "GET",
            f"/api/v1/diagnostic/processlist/?instance_id={target.instance_id}&command_type=ALL",
            expected={200, 400, 403},
            domain="observability",
        )
    else:
        add_skip(
            results,
            target,
            "会话/活动采集",
            f"{target.db_type} 使用 SQL 洞察只读链路，不承诺会话列表",
            domain="observability",
            promised=False,
        )

    if args.collect_sql_activity:
        run_check(
            results,
            client,
            target,
            "手动触发 SQL 活动采集",
            "POST",
            f"/api/v1/slowlog/collect/?instance_id={target.instance_id}&limit=20",
            expected={200, 400, 403},
            domain="observability",
            promised=True,
        )
    else:
        add_skip(
            results,
            target,
            "手动触发 SQL 活动采集",
            "未开启 --collect-sql-activity；默认不写入采集记录",
            domain="observability",
            promised=False,
        )


def summarize_matrix(results: list[CheckResult]) -> list[dict[str, Any]]:
    matrix: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        key = (result.target, result.domain)
        row = matrix.setdefault(
            key,
            {
                "target": result.target,
                "domain": result.domain,
                "domain_label": DOMAIN_LABELS.get(result.domain, result.domain),
                "promised": False,
                "passed": 0,
                "skipped": 0,
                "failed": 0,
                "promised_skipped": 0,
            },
        )
        row["promised"] = bool(row["promised"] or result.promised)
        if result.skipped:
            row["skipped"] += 1
            if result.promised:
                row["promised_skipped"] += 1
        elif result.ok:
            row["passed"] += 1
        else:
            row["failed"] += 1
    return [matrix[key] for key in sorted(matrix)]


def print_matrix_summary(results: list[CheckResult]) -> None:
    print("\n客户验收矩阵：")
    for row in summarize_matrix(results):
        promise = "PROMISED" if row["promised"] else "NOT-PROMISED"
        status = "FAIL" if row["failed"] else "UNVERIFIED" if row["promised_skipped"] else "PASS"
        print(
            f"- {row['target']} / {row['domain_label']} / {promise}: {status} "
            f"({row['passed']} 通过，{row['skipped']} 跳过，"
            f"{row['failed']} 失败，{row['promised_skipped']} 个承诺项未验证)"
        )


def write_reports(results: list[CheckResult], targets: list[Target], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"engine-validation-{stamp}.json"
    md_path = out_dir / f"engine-validation-{stamp}.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "targets": [target.__dict__ for target in targets],
        "domains": DOMAIN_LABELS,
        "matrix": summarize_matrix(results),
        "results": [result.__dict__ for result in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 客户验证后交付引擎实测记录",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 目标数量：{len(targets)}",
        "",
        "## 验收矩阵",
        "",
        "| Target | Domain | Promise | Status | Passed | Skipped | Failed | Promised skipped |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in payload["matrix"]:
        promise = "PROMISED" if row["promised"] else "NOT-PROMISED"
        status = "FAIL" if row["failed"] else "UNVERIFIED" if row["promised_skipped"] else "PASS"
        lines.append(
            f"| {row['target']} | {row['domain_label']} | {promise} | {status} | "
            f"{row['passed']} | {row['skipped']} | {row['failed']} | {row['promised_skipped']} |"
        )
    lines.extend(
        [
            "",
            "## 检查明细",
            "",
            "| Target | Domain | Promise | Check | Result | Detail |",
            "|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        marker = "SKIP" if result.skipped else "PASS" if result.ok else "FAIL"
        promise = "PROMISED" if result.promised else "NOT-PROMISED"
        domain = DOMAIN_LABELS.get(result.domain, result.domain)
        detail = result.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {result.target} | {domain} | {promise} | {result.name} | {marker} | {detail} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sagitta Control customer engine validation")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="db_type|instance_id|db_name|table_name|read_sql",
    )
    parser.add_argument("--target-file", default="")
    parser.add_argument("--limit-num", type=int, default=100)
    parser.add_argument("--sync-databases", action="store_true")
    parser.add_argument("--execute-readonly-query", action="store_true")
    parser.add_argument("--submit-workflow-boundary", action="store_true")
    parser.add_argument(
        "--collect-sql-activity",
        action="store_true",
        help="显式触发 SQL 活动采集；默认不写入采集记录",
    )
    parser.add_argument(
        "--strict-promised",
        action="store_true",
        help="承诺项被跳过时也返回失败，用于正式客户验收门禁",
    )
    parser.add_argument("--group-id", type=int, default=None)
    parser.add_argument("--flow-id", type=int, default=None)
    parser.add_argument(
        "--out-dir",
        default="artifacts/reports/customer-engine-validation",
        help="JSON/Markdown 记录输出目录",
    )
    args = parser.parse_args()

    try:
        targets = load_targets(args)
        public_client = ApiClient(args.base_url, timeout=args.timeout)
        token = args.token or login(public_client, args.username, args.password)
        client = ApiClient(args.base_url, token=token, timeout=args.timeout)
        results: list[CheckResult] = []
        for target in targets:
            validate_target(client, target, args, results)
        print_matrix_summary(results)
        write_reports(results, targets, Path(args.out_dir))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    failed = sum(1 for result in results if not result.ok)
    skipped = sum(1 for result in results if result.skipped)
    promised_skipped = sum(1 for result in results if result.skipped and result.promised)
    passed = len(results) - failed - skipped
    print(
        f"客户验证后交付引擎实测完成：{passed} 通过，{skipped} 跳过，"
        f"{failed} 失败，{promised_skipped} 个承诺项未验证。"
    )
    if failed:
        return 1
    if args.strict_promised and promised_skipped:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
