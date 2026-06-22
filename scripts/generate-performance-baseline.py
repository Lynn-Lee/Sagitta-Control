#!/usr/bin/env python3
"""生成 Sagitta Control 性能基线报告。

脚本可读取 Locust CSV 输出；当 frontend/dist 存在时，会同时写入前端包体预算。
输出的 Markdown 报告可归档到客户交付记录中。
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class EndpointStat:
    name: str
    requests: int
    failures: int
    median_ms: float
    p95_ms: float
    avg_ms: float
    rps: float


@dataclass
class AssetStat:
    name: str
    kind: str
    kib: float
    gzip_kib: float


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def read_locust_stats(path: Path) -> list[EndpointStat]:
    if not path.exists():
        return []
    rows: list[EndpointStat] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = row.get("Name") or row.get("name") or ""
            if not name or name == "Aggregated":
                continue
            rows.append(
                EndpointStat(
                    name=name,
                    requests=_int(row.get("Request Count")),
                    failures=_int(row.get("Failure Count")),
                    median_ms=_float(row.get("Median Response Time")),
                    p95_ms=_float(row.get("95%")),
                    avg_ms=_float(row.get("Average Response Time")),
                    rps=_float(row.get("Requests/s")),
                )
            )
    return rows


def read_assets(dist_dir: Path) -> list[AssetStat]:
    assets_dir = dist_dir / "assets"
    if not assets_dir.exists():
        return []
    stats: list[AssetStat] = []
    for path in assets_dir.iterdir():
        if path.suffix not in {".js", ".css"}:
            continue
        raw = path.read_bytes()
        stats.append(
            AssetStat(
                name=path.name,
                kind=path.suffix.lstrip("."),
                kib=len(raw) / 1024,
                gzip_kib=len(gzip.compress(raw)) / 1024,
            )
        )
    return sorted(stats, key=lambda item: item.kib, reverse=True)


def capacity_tier(concurrent_users: int, rps: float) -> dict[str, str]:
    load = max(concurrent_users, int(rps * 10))
    if load <= 50:
        return {
            "tier": "small",
            "api": "2 vCPU / 4 GiB",
            "postgres": "2 vCPU / 4 GiB / 100 GiB SSD",
            "redis": "1 vCPU / 1 GiB",
            "workers": "2 workers, concurrency=2",
            "retention": "查询/审计日志保留 90 天，SQL 洞察 30 天",
        }
    if load <= 200:
        return {
            "tier": "medium",
            "api": "4 vCPU / 8 GiB",
            "postgres": "4 vCPU / 8 GiB / 300 GiB SSD",
            "redis": "2 vCPU / 2 GiB",
            "workers": "3-4 workers, concurrency=4",
            "retention": "查询/审计日志保留 180 天，SQL 洞察 60 天",
        }
    return {
        "tier": "large",
        "api": "8 vCPU / 16 GiB 起",
        "postgres": "8 vCPU / 16 GiB / 500 GiB+ SSD，建议独立实例",
        "redis": "2-4 vCPU / 4 GiB",
        "workers": "6+ workers, concurrency=4-8，按 execute/archive/notify 拆队列扩容",
        "retention": "按合规要求分表/归档，SQL 洞察建议 30-60 天",
    }


def render_report(
    args: argparse.Namespace,
    endpoints: list[EndpointStat],
    assets: list[AssetStat],
) -> str:
    total_requests = sum(item.requests for item in endpoints)
    total_failures = sum(item.failures for item in endpoints)
    total_rps = sum(item.rps for item in endpoints)
    p95_max = max((item.p95_ms for item in endpoints), default=0)
    tier = capacity_tier(args.concurrent_users, total_rps)
    generated_at = datetime.now().isoformat(timespec="seconds")

    lines = [
        "# Sagitta Control 性能基线与容量建议",
        "",
        f"- 生成时间：{generated_at}",
        f"- 测试环境：{args.environment}",
        f"- 并发用户：{args.concurrent_users}",
        f"- 测试时长：{args.duration}",
        "- 说明：无 Locust CSV 时，本报告作为可执行基线模板；接入 CSV 后自动填充接口指标。",
        "",
        "## 汇总",
        "",
        f"- 请求总数：{total_requests or '未提供'}",
        f"- 失败总数：{total_failures}",
        f"- 汇总 RPS：{total_rps:.2f}" if endpoints else "- 汇总 RPS：未提供",
        f"- 最大 P95：{p95_max:.0f} ms" if endpoints else "- 最大 P95：未提供",
        f"- 建议容量档位：{tier['tier']}",
        "",
        "## 接口延迟",
        "",
        "| Endpoint | Requests | Failures | Avg ms | Median ms | P95 ms | RPS |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    if endpoints:
        for item in sorted(endpoints, key=lambda row: row.p95_ms, reverse=True):
            lines.append(
                f"| {item.name} | {item.requests} | {item.failures} | "
                f"{item.avg_ms:.0f} | {item.median_ms:.0f} | {item.p95_ms:.0f} | {item.rps:.2f} |"
            )
    else:
        lines.append("| 未提供 Locust CSV |  |  |  |  |  |  |")

    lines.extend(
        [
            "",
            "## 前端包体",
            "",
            "| Asset | Type | Raw KiB | Gzip KiB |",
            "|---|---|---:|---:|",
        ]
    )
    if assets:
        for asset in assets[:12]:
            lines.append(f"| {asset.name} | {asset.kind} | {asset.kib:.1f} | {asset.gzip_kib:.1f} |")
    else:
        lines.append("| 未找到 frontend/dist/assets |  |  |  |")

    lines.extend(
        [
            "",
            "## 容量建议",
            "",
            f"- API/前端容器：{tier['api']}",
            f"- PostgreSQL：{tier['postgres']}",
            f"- Redis：{tier['redis']}",
            f"- Celery Worker：{tier['workers']}",
            f"- 数据保留：{tier['retention']}",
            "",
            "## 交付建议",
            "",
            "- 接口 P95 超过客户 SLA、失败率不为 0、或核心页面包体超过预算时，不建议生成正式交付包。",
            "- 归档、执行、通知队列应在客户峰值窗口单独观察队列长度和重试率。",
            "- 本报告建议与预检脚本、验收脚本输出一起归档到发布或客户项目档案。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Sagitta Control 性能基线报告")
    parser.add_argument("--locust-stats", default="", help="Locust *_stats.csv 文件路径")
    parser.add_argument("--frontend-dist", default="frontend/dist")
    parser.add_argument("--environment", default="local or customer staging")
    parser.add_argument("--concurrent-users", type=int, default=50)
    parser.add_argument("--duration", default="10m")
    parser.add_argument("--out", default="artifacts/reports/performance/performance_report.md")
    args = parser.parse_args()

    endpoints = read_locust_stats(Path(args.locust_stats)) if args.locust_stats else []
    assets = read_assets(Path(args.frontend_dist))
    report = render_report(args, endpoints, assets)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Performance baseline report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
