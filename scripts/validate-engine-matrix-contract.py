#!/usr/bin/env python3
"""Validate that engine support metadata stays aligned with implementation.

This is a CI-friendly contract check. Real database validation still happens
with scripts/customer-engine-validation.py against customer-like environments.
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
        fail("customer-engine-validation.py must expose SUPPORTED_ENGINE_TYPES")
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
        fail(f"Duplicate ENGINE_MATRIX db_type entries: {sorted(duplicates)}")

    missing = registry_types - set(matrix_types)
    extra = set(matrix_types) - registry_types
    if missing:
        fail(f"ENGINE_MATRIX missing registered engines: {sorted(missing)}")
    if extra:
        fail(f"ENGINE_MATRIX contains unregistered engines: {sorted(extra)}")

    for entry in matrix_entries:
        db_type = str(entry.get("db_type", "")).lower()
        support_level = str(entry.get("support_level", ""))
        if support_level not in SUPPORTED_LEVELS:
            fail(f"{db_type} has unsupported support_level: {support_level}")

        capabilities = entry.get("capabilities")
        if not isinstance(capabilities, dict):
            fail(f"{db_type} capabilities must be a dict")
        capability_keys = set(capabilities.keys())
        if capability_keys != EXPECTED_CAPABILITIES:
            fail(
                f"{db_type} capability keys mismatch. "
                f"missing={sorted(EXPECTED_CAPABILITIES - capability_keys)} "
                f"extra={sorted(capability_keys - EXPECTED_CAPABILITIES)}"
            )
        non_boolean = [key for key, value in capabilities.items() if not isinstance(value, bool)]
        if non_boolean:
            fail(f"{db_type} capabilities must be boolean: {non_boolean}")

        validation_required = str(entry.get("validation_required", "")).strip()
        if not validation_required:
            fail(f"{db_type} must describe validation_required")

        if support_level == "validated_minimal" and db_type not in customer_validation_types:
            fail(f"{db_type} validated_minimal engine is missing from customer validation script")

    unused_validation_types = customer_validation_types - set(matrix_types)
    if unused_validation_types:
        fail(f"customer validation script contains unknown engines: {sorted(unused_validation_types)}")

    print(
        "Engine matrix contract passed: "
        f"{len(matrix_entries)} matrix entries, {len(registry_types)} registered engines."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
