"""交付支持材料自检。"""

from __future__ import annotations

import json
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from app.services.commercial_ops_metadata import (
    COMMERCIAL_VERSION,
    DELIVERY_MANIFEST_PATH,
    DELIVERY_PREFLIGHT_DEFINITIONS,
)


def project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            return parent
    return Path.cwd()


def load_delivery_manifest() -> dict[str, Any] | None:
    manifest_path = Path(os.getenv("COMMERCIAL_DELIVERY_MANIFEST") or DELIVERY_MANIFEST_PATH)
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != COMMERCIAL_VERSION or not isinstance(data.get("materials"), list):
        return None
    return data


def manifest_materials(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not manifest:
        return {}
    materials: dict[str, dict[str, Any]] = {}
    for item in manifest.get("materials", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            materials[item["path"]] = item
    return materials


def preflight_detail(
    ok: bool,
    ready: list[str],
    missing: list[str],
    non_executable: list[str],
) -> str:
    if ok:
        return "已就绪：" + "、".join(ready)
    parts = []
    if missing:
        parts.append("未找到：" + "、".join(missing))
    if non_executable:
        parts.append("不可执行：" + "、".join(non_executable))
    return "；".join(parts) or "未满足交付自检要求"


def evaluate_preflight_definition(
    root: Path,
    definition: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = [str(item) for item in definition["paths"]]
    kind = str(definition["kind"])
    ready: list[str] = []
    missing: list[str] = []
    non_executable: list[str] = []

    if kind == "glob":
        for pattern in paths:
            matches = sorted(root.glob(pattern))
            if matches:
                ready.extend(str(path.relative_to(root)) for path in matches[:3])
                if len(matches) > 3:
                    ready.append(f"{pattern} 等 {len(matches)} 个文件")
            else:
                missing.append(pattern)
        ok = not missing
    elif kind == "all_executable":
        for relative in paths:
            path = root / relative
            if not path.exists():
                missing.append(relative)
            elif not os.access(path, os.X_OK):
                non_executable.append(relative)
            else:
                ready.append(relative)
        ok = not missing and not non_executable
    else:
        for relative in paths:
            path = root / relative
            if not path.exists():
                missing.append(relative)
                continue
            if kind == "executable" and not os.access(path, os.X_OK):
                non_executable.append(relative)
                continue
            ready.append(relative)
        ok = bool(ready)
        if ok:
            missing = []
            non_executable = []

    manifest_items = manifest_materials(manifest)
    if not ok and manifest_items:
        manifest_ready: list[str] = []
        manifest_missing: list[str] = []
        manifest_non_executable: list[str] = []
        if kind == "glob":
            for pattern in paths:
                manifest_matches = sorted(path for path in manifest_items if fnmatch(path, pattern))
                if manifest_matches:
                    manifest_ready.extend(manifest_matches[:3])
                else:
                    manifest_missing.append(pattern)
            ok = not manifest_missing
        elif kind == "all_executable":
            for relative in paths:
                item = manifest_items.get(relative)
                if not item:
                    manifest_missing.append(relative)
                elif not item.get("executable", False):
                    manifest_non_executable.append(relative)
                else:
                    manifest_ready.append(relative)
            ok = not manifest_missing and not manifest_non_executable
        else:
            for relative in paths:
                item = manifest_items.get(relative)
                if not item:
                    manifest_missing.append(relative)
                    continue
                if kind == "executable" and not item.get("executable", False):
                    manifest_non_executable.append(relative)
                    continue
                manifest_ready.append(relative)
            ok = bool(manifest_ready)
        if ok:
            ready = [f"{item}（发布清单）" for item in manifest_ready]
            missing = []
            non_executable = []
        else:
            missing = manifest_missing or missing
            non_executable = manifest_non_executable or non_executable

    return {
        "key": definition["key"],
        "label": definition["label"],
        "name": definition["name"],
        "ok": ok,
        "blocking": bool(definition["blocking"]),
        "detail": preflight_detail(ok, ready, missing, non_executable),
        "path": definition["path"],
    }


def delivery_preflight(
    root: Path | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    manifest_data: dict[str, Any] | None
    if manifest is not None:
        manifest_data = manifest
    elif root is None:
        manifest_data = load_delivery_manifest()
    else:
        manifest_data = None
    checks = [
        evaluate_preflight_definition(base, definition, manifest_data)
        for definition in DELIVERY_PREFLIGHT_DEFINITIONS
    ]
    failed_blockers = [item for item in checks if item["blocking"] and not item["ok"]]
    failed_optional = [item for item in checks if not item["blocking"] and not item["ok"]]
    return {
        "root": str(base),
        "status": "blocked" if failed_blockers else "needs_configuration" if failed_optional else "ready",
        "checks": checks,
    }
