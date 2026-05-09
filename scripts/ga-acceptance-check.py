#!/usr/bin/env python3
"""SagittaDB v1.0-GA acceptance smoke check.

By default this script only runs non-mutating checks. Mutating business checks
such as workflow submission, query privilege application, archive job submission,
license activation, and notification test require explicit flags.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    skipped: bool = False


class ApiClient:
    def __init__(
        self, base_url: str, token: str | None = None, timeout: int = 10
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
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


def check_endpoint(
    client: ApiClient, name: str, path: str, expected: set[int] | None = None
) -> CheckResult:
    expected = expected or {200}
    return check_request(client, name, "GET", path, expected=expected)


def check_request(
    client: ApiClient,
    name: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    expected: set[int] | None = None,
) -> CheckResult:
    expected = expected or {200}
    try:
        status, payload = client.request(method, path, body)
    except Exception as exc:  # noqa: BLE001 - acceptance output should keep going
        return CheckResult(name, False, f"request failed: {exc}")

    if status in expected:
        return CheckResult(name, True, f"HTTP {status}")
    return CheckResult(name, False, f"HTTP {status}: {payload}")


def skip_check(name: str, reason: str) -> CheckResult:
    return CheckResult(name, True, reason, skipped=True)


def login(
    client: ApiClient, username: str, password: str
) -> tuple[str | None, CheckResult]:
    try:
        status, payload = client.request(
            "POST",
            "/api/v1/auth/login/",
            {"username": username, "password": password},
        )
    except Exception as exc:  # noqa: BLE001
        return None, CheckResult("登录", False, f"request failed: {exc}")

    if status != 200:
        return None, CheckResult("登录", False, f"HTTP {status}: {payload}")
    if payload.get("password_change_required"):
        return None, CheckResult("登录", False, "账号需要先修改密码")
    if payload.get("requires_2fa"):
        return None, CheckResult(
            "登录", False, "账号启用了 2FA，本脚本不处理交互验证码"
        )
    token = payload.get("access_token")
    if not token:
        return None, CheckResult("登录", False, "未返回 access_token")
    return str(token), CheckResult("登录", True, "获取 access_token")


def print_results(results: list[CheckResult]) -> int:
    failed = 0
    skipped = 0
    for result in results:
        if result.skipped:
            marker = "SKIP"
            skipped += 1
        else:
            marker = "PASS" if result.ok else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}")
        if not result.ok:
            failed += 1
    passed = len(results) - failed - skipped
    print(f"\n验收检查完成：{passed} 通过，{skipped} 跳过，{failed} 失败。")
    return 1 if failed else 0


def workflow_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "instance_id": args.instance_id,
        "db_name": args.db_name,
        "sql_content": args.sql,
    }


def query_privilege_payload(args: argparse.Namespace) -> dict[str, Any]:
    valid_date = (date.today() + timedelta(days=args.query_privilege_days)).isoformat()
    scope_type = args.query_scope
    table_name = args.table_name if scope_type == "table" else ""
    db_name = "" if scope_type == "instance" else args.db_name
    return {
        "title": args.query_privilege_title,
        "instance_id": args.instance_id,
        "group_id": args.group_id,
        "flow_id": args.flow_id,
        "db_name": db_name,
        "table_name": table_name,
        "scope_type": scope_type,
        "valid_date": valid_date,
        "limit_num": args.limit_num,
        "priv_type": 2 if scope_type == "table" else 1,
        "apply_reason": args.apply_reason,
        "risk_remark": args.risk_remark,
        "audit_auth_groups": "",
    }


def archive_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "source_instance_id": args.instance_id,
        "source_db": args.db_name,
        "source_table": args.table_name,
        "condition": args.archive_condition,
        "archive_mode": args.archive_mode,
        "dest_instance_id": args.dest_instance_id,
        "dest_db": args.dest_db,
        "dest_table": args.dest_table,
        "batch_size": args.archive_batch_size,
        "sleep_ms": args.archive_sleep_ms,
        "dry_run": True,
        "apply_reason": args.apply_reason,
        "risk_remark": args.risk_remark,
        "flow_id": args.flow_id,
    }


def add_core_functional_checks(
    results: list[CheckResult],
    client: ApiClient,
    args: argparse.Namespace,
) -> None:
    results.append(check_endpoint(client, "归档支持矩阵", "/api/v1/archive/support/"))

    if not args.instance_id:
        results.extend(
            [
                skip_check(
                    "SQL 工单风险预案", "未提供 --instance-id，跳过实例相关检查"
                ),
                skip_check(
                    "在线查询权限排查", "未提供 --instance-id，跳过实例相关检查"
                ),
                skip_check(
                    "查询权限风险预案", "未提供 --instance-id，跳过实例相关检查"
                ),
                skip_check(
                    "数据字典注册库列表", "未提供 --instance-id，跳过实例相关检查"
                ),
            ]
        )
        return

    results.extend(
        [
            check_request(
                client,
                "SQL 工单风险预案",
                "POST",
                "/api/v1/workflow/risk-plan/",
                workflow_payload(args),
            ),
            check_request(
                client,
                "在线查询权限排查",
                "POST",
                "/api/v1/query/access-check/",
                {
                    "instance_id": args.instance_id,
                    "db_name": args.db_name,
                    "sql": args.sql,
                    "limit_num": args.limit_num,
                },
                expected={200, 403},
            ),
            check_request(
                client,
                "查询权限风险预案",
                "POST",
                "/api/v1/query/privileges/risk-plan/",
                query_privilege_payload(args),
            ),
            check_endpoint(
                client,
                "数据字典注册库列表",
                f"/api/v1/instances/{args.instance_id}/db-list/?page=1&page_size=20",
            ),
        ]
    )


def add_explicit_mutating_checks(
    results: list[CheckResult],
    client: ApiClient,
    args: argparse.Namespace,
) -> None:
    if args.submit_workflow:
        if args.instance_id:
            body = {
                "workflow_name": args.workflow_name,
                "group_id": args.group_id,
                "flow_id": args.flow_id,
                "instance_id": args.instance_id,
                "db_name": args.db_name,
                "sql_content": args.sql,
                "is_backup": False,
                "risk_remark": args.risk_remark,
            }
            results.append(
                check_request(
                    client, "提交 SQL 工单", "POST", "/api/v1/workflow/", body
                )
            )
        else:
            results.append(skip_check("提交 SQL 工单", "缺少 --instance-id"))

    if args.apply_query_privilege:
        if args.instance_id:
            results.append(
                check_request(
                    client,
                    "提交查询权限申请",
                    "POST",
                    "/api/v1/query/privileges/apply/",
                    query_privilege_payload(args),
                )
            )
        else:
            results.append(skip_check("提交查询权限申请", "缺少 --instance-id"))

    if args.submit_archive:
        if args.instance_id and args.table_name:
            results.append(
                check_request(
                    client,
                    "提交归档作业",
                    "POST",
                    "/api/v1/archive/run/",
                    archive_payload(args),
                )
            )
        else:
            results.append(
                skip_check("提交归档作业", "缺少 --instance-id 或 --table-name")
            )

    if args.activate_license:
        if args.activation_code or args.customer_id:
            results.append(
                check_request(
                    client,
                    "生成离线 License Challenge",
                    "POST",
                    "/api/v1/system/license/challenge",
                    {"customer_id": args.customer_id},
                )
            )
            results.append(
                check_request(
                    client,
                    "在线激活 License",
                    "POST",
                    "/api/v1/system/license/activate",
                    {
                        "activation_code": args.activation_code,
                        "customer_id": args.customer_id,
                    },
                )
            )
        else:
            results.append(
                skip_check(
                    "在线激活 License", "缺少 --activation-code 或 --customer-id"
                )
            )

    if args.refresh_license:
        results.append(
            check_request(
                client, "在线刷新 License", "POST", "/api/v1/system/license/refresh"
            )
        )

    if args.notify_user_id:
        results.append(
            check_request(
                client,
                "发送通知测试",
                "POST",
                "/api/v1/system/config/test/notify-user/",
                {"user_id": args.notify_user_id},
            )
        )


def needs_authenticated_checks(args: argparse.Namespace) -> bool:
    return bool(
        args.instance_id
        or args.submit_workflow
        or args.apply_query_privilege
        or args.submit_archive
        or args.activate_license
        or args.refresh_license
        or args.notify_user_id
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SagittaDB v1.0-GA acceptance smoke check"
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="Backend base URL"
    )
    parser.add_argument(
        "--username",
        default="",
        help="Admin or auditor username for authenticated checks",
    )
    parser.add_argument(
        "--password", default="", help="Password for authenticated checks"
    )
    parser.add_argument(
        "--token", default="", help="Existing bearer token for authenticated checks"
    )
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout seconds")
    parser.add_argument(
        "--instance-id",
        type=int,
        default=0,
        help="Instance ID for instance-scoped checks",
    )
    parser.add_argument(
        "--db-name", default="test_db", help="Database/schema name for instance checks"
    )
    parser.add_argument(
        "--table-name", default="", help="Table name for table/archive checks"
    )
    parser.add_argument(
        "--sql", default="SELECT 1", help="Read-only SQL used by query/workflow checks"
    )
    parser.add_argument(
        "--limit-num", type=int, default=100, help="Query limit for query checks"
    )
    parser.add_argument(
        "--group-id",
        type=int,
        default=None,
        help="Resource group ID for mutating submissions",
    )
    parser.add_argument(
        "--flow-id",
        type=int,
        default=None,
        help="Approval flow ID for mutating submissions",
    )
    parser.add_argument(
        "--apply-reason", default="GA 验收脚本自动提交", help="Reason for apply actions"
    )
    parser.add_argument(
        "--risk-remark", default="GA 验收脚本验证，可按验收记录清理", help="Risk remark"
    )
    parser.add_argument(
        "--workflow-name", default="GA 验收 SQL 工单", help="Workflow name"
    )
    parser.add_argument(
        "--query-privilege-title",
        default="GA 验收查询权限申请",
        help="Query privilege title",
    )
    parser.add_argument(
        "--query-scope", choices=["instance", "database", "table"], default="database"
    )
    parser.add_argument(
        "--query-privilege-days",
        type=int,
        default=7,
        help="Query privilege validity days",
    )
    parser.add_argument("--archive-mode", choices=["purge", "dest"], default="purge")
    parser.add_argument(
        "--archive-condition", default="1=0", help="Archive WHERE condition"
    )
    parser.add_argument("--archive-batch-size", type=int, default=1000)
    parser.add_argument("--archive-sleep-ms", type=int, default=100)
    parser.add_argument("--dest-instance-id", type=int, default=None)
    parser.add_argument("--dest-db", default=None)
    parser.add_argument("--dest-table", default=None)
    parser.add_argument("--activation-code", default="")
    parser.add_argument("--customer-id", default="")
    parser.add_argument(
        "--notify-user-id",
        type=int,
        default=0,
        help="Send notification test to user ID",
    )
    parser.add_argument(
        "--submit-workflow", action="store_true", help="Create a SQL workflow"
    )
    parser.add_argument(
        "--apply-query-privilege",
        action="store_true",
        help="Create a query privilege apply",
    )
    parser.add_argument(
        "--submit-archive", action="store_true", help="Create an archive job"
    )
    parser.add_argument(
        "--activate-license", action="store_true", help="Call online license activation"
    )
    parser.add_argument(
        "--refresh-license", action="store_true", help="Call online license refresh"
    )
    args = parser.parse_args()

    public_client = ApiClient(args.base_url, timeout=args.timeout)
    results = [
        check_endpoint(public_client, "后端健康检查", "/health"),
    ]

    if args.token:
        token = args.token
        results.append(CheckResult("登录", True, "使用 --token 跳过用户名密码登录"))
    elif not args.username or not args.password:
        if needs_authenticated_checks(args):
            results.append(
                CheckResult(
                    "认证参数",
                    False,
                    "实例或写入类验收需要提供 --username/--password 或 --token",
                )
            )
            return print_results(results)
        results.append(
            CheckResult(
                "认证读路径",
                True,
                "未提供 --username/--password，已跳过认证接口检查",
            )
        )
        return print_results(results)
    else:
        token, login_result = login(public_client, args.username, args.password)
        results.append(login_result)
        if not token:
            return print_results(results)

    authed_client = ApiClient(args.base_url, token=token, timeout=args.timeout)
    results.extend(
        [
            check_endpoint(authed_client, "当前用户信息", "/api/v1/auth/me/"),
            check_endpoint(
                authed_client, "License 状态", "/api/v1/system/license/status"
            ),
            check_endpoint(
                authed_client, "实例列表", "/api/v1/instances/?page=1&page_size=1"
            ),
            check_endpoint(
                authed_client, "SQL 工单列表", "/api/v1/workflow/?page=1&page_size=1"
            ),
            check_endpoint(
                authed_client,
                "查询权限申请列表",
                "/api/v1/query/privileges/applies/?page=1&page_size=1",
            ),
            check_endpoint(
                authed_client, "查询历史", "/api/v1/query/logs/?page=1&page_size=1"
            ),
            check_endpoint(
                authed_client,
                "归档作业列表",
                "/api/v1/archive/jobs/?page=1&page_size=1",
            ),
            check_endpoint(
                authed_client,
                "操作审计日志",
                "/api/v1/system/audit-logs/?page=1&page_size=1",
            ),
            check_endpoint(
                authed_client,
                "Dashboard 在线查询概览",
                "/api/v1/monitor/dashboard/query-overview/",
            ),
            check_endpoint(
                authed_client,
                "Dashboard 工单概览",
                "/api/v1/monitor/dashboard/workflow-overview/",
            ),
        ]
    )
    add_core_functional_checks(results, authed_client, args)
    add_explicit_mutating_checks(results, authed_client, args)
    return print_results(results)


if __name__ == "__main__":
    sys.exit(main())
