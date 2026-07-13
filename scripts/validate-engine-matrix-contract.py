#!/usr/bin/env python3
"""校验引擎支持矩阵与实际实现保持一致。

该脚本用于 CI 合同检查；真实数据库验证仍由
scripts/customer-engine-validation.py 在客户同构环境中执行。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

EXPECTED_CAPABILITIES = {
    "connection",
    "schema",
    "query",
    "workflow",
    "archive",
    "monitor",
    "session",
    "explain",
    "kill_session",
}
SUPPORTED_LEVELS = {"ga", "validated_minimal", "read_only_metadata"}


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def load_customer_validation_types() -> set[str]:
    script_path = ROOT / "scripts" / "customer-engine-validation.py"
    spec = importlib.util.spec_from_file_location("customer_engine_validation", script_path)
    if spec is None or spec.loader is None:
        fail(f"Unable to load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    supported = getattr(module, "SUPPORTED_ENGINE_TYPES", None)
    if not isinstance(supported, set):
        fail("customer-engine-validation.py 必须暴露 SUPPORTED_ENGINE_TYPES")
    return {str(item).lower() for item in supported}


def main() -> int:
    from app.engines.registry import supported_engines
    from app.services.commercial_ops import ENGINE_MATRIX

    registry_types = set(supported_engines())
    matrix_entries: list[dict[str, Any]] = list(ENGINE_MATRIX)
    matrix_types = [str(item.get("db_type", "")).lower() for item in matrix_entries]
    customer_validation_types = load_customer_validation_types()

    duplicates = {db_type for db_type in matrix_types if matrix_types.count(db_type) > 1}
    if duplicates:
        fail(f"ENGINE_MATRIX 存在重复 db_type：{sorted(duplicates)}")

    missing = registry_types - set(matrix_types)
    extra = set(matrix_types) - registry_types
    if missing:
        fail(f"ENGINE_MATRIX 缺少已注册引擎：{sorted(missing)}")
    if extra:
        fail(f"ENGINE_MATRIX 包含未注册引擎：{sorted(extra)}")

    for entry in matrix_entries:
        db_type = str(entry.get("db_type", "")).lower()
        support_level = str(entry.get("support_level", ""))
        if support_level not in SUPPORTED_LEVELS:
            fail(f"{db_type} 使用了不支持的 support_level：{support_level}")

        capabilities = entry.get("capabilities")
        if not isinstance(capabilities, dict):
            fail(f"{db_type} capabilities 必须是 dict")
        capability_keys = set(capabilities.keys())
        if capability_keys != EXPECTED_CAPABILITIES:
            fail(
                f"{db_type} capability keys 不匹配。"
                f"missing={sorted(EXPECTED_CAPABILITIES - capability_keys)} "
                f"extra={sorted(capability_keys - EXPECTED_CAPABILITIES)}"
            )
        non_boolean = [key for key, value in capabilities.items() if not isinstance(value, bool)]
        if non_boolean:
            fail(f"{db_type} capabilities 必须是布尔值：{non_boolean}")

        validation_required = str(entry.get("validation_required", "")).strip()
        if not validation_required:
            fail(f"{db_type} 必须填写 validation_required")

        if support_level == "validated_minimal" and db_type not in customer_validation_types:
            fail(f"{db_type} validated_minimal 引擎未出现在客户同构验证脚本中")

    unused_validation_types = customer_validation_types - set(matrix_types)
    if unused_validation_types:
        fail(f"客户同构验证脚本包含未知引擎：{sorted(unused_validation_types)}")

    print(
        "引擎支持矩阵合同校验通过："
        f"{len(matrix_entries)} 个矩阵条目，{len(registry_types)} 个已注册引擎。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
