"""商业化运营、交付验收、合规报表和支持矩阵服务。"""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.approval_flow import ApprovalFlow
from app.models.archive import ArchiveJob
from app.models.instance import Instance, InstanceDatabase
from app.models.monitor import MonitorCollectConfig, MonitorMetricSnapshot
from app.models.query import QueryLog, QueryPrivilege, QueryPrivilegeApply
from app.models.role import UserGroup
from app.models.system import (
    DeliveryAcceptanceRun,
    DiagnosticBundle,
    NotificationDeliveryLog,
    OperationLog,
    SystemConfig,
)
from app.models.user import ResourceGroup, Users
from app.models.workflow import SqlWorkflow
from app.services.license import (
    LICENSE_PROJECT_CODE,
    LICENSE_PROJECT_NAME,
    LicenseService,
)
from app.services.system_config import SystemConfigService

COMMERCIAL_VERSION = "2.1.4"

ONBOARDING_STEPS = [
    {"key": "branding", "label": "品牌配置", "path": "/system/config"},
    {"key": "license", "label": "License 授权", "path": "/system/license"},
    {"key": "auth", "label": "认证方式", "path": "/system/config"},
    {"key": "notification", "label": "通知渠道", "path": "/system/config"},
    {"key": "first_instance", "label": "首个实例", "path": "/instance"},
    {"key": "governance", "label": "资源组/用户组/审批流", "path": "/system/groups"},
    {"key": "acceptance", "label": "验收报告", "path": "/commercial"},
]

RETENTION_DEFAULTS = {
    "operation_audit": 365,
    "query_history": 180,
    "notification_log": 90,
    "diagnostic_sampling": 30,
}

RETENTION_LABELS = {
    "operation_audit": "操作审计",
    "query_history": "查询历史",
    "notification_log": "通知日志",
    "diagnostic_sampling": "诊断采样",
}

DELIVERY_PREFLIGHT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "backup_script",
        "label": "备份脚本",
        "name": "备份脚本",
        "blocking": True,
        "kind": "executable",
        "paths": ["deploy/backup/backup-postgres.sh", "backup-postgres.sh"],
        "path": "/commercial",
    },
    {
        "key": "restore_script",
        "label": "恢复脚本",
        "name": "恢复脚本",
        "blocking": True,
        "kind": "executable",
        "paths": ["deploy/backup/restore-postgres.sh", "restore-postgres.sh"],
        "path": "/commercial",
    },
    {
        "key": "upgrade_script",
        "label": "升级回滚脚本",
        "name": "升级回滚脚本",
        "blocking": True,
        "kind": "executable",
        "paths": [
            "deploy/customer/upgrade.sh",
            f"dist-commercial/SagittaDB-Enterprise-v{COMMERCIAL_VERSION}/upgrade.sh",
            "upgrade.sh",
        ],
        "path": "/commercial",
    },
    {
        "key": "commercial_guard_scripts",
        "label": "商业构建门禁脚本",
        "name": "商业构建门禁脚本",
        "blocking": True,
        "kind": "all_executable",
        "paths": [
            "scripts/validate-commercial-build-context.sh",
            "scripts/validate-commercial-images.sh",
            "scripts/generate-commercial-sbom.sh",
            "scripts/sign-commercial-artifacts.sh",
        ],
        "path": "/commercial",
    },
    {
        "key": "customer_package_checksum",
        "label": "客户包 sha256",
        "name": "客户包 sha256",
        "blocking": False,
        "kind": "file",
        "paths": [f"dist-commercial/SagittaDB-Enterprise-v{COMMERCIAL_VERSION}.zip.sha256"],
        "path": "/commercial",
    },
    {
        "key": "customer_package_signature",
        "label": "客户包签名",
        "name": "客户包签名",
        "blocking": False,
        "kind": "file",
        "paths": [
            f"dist-commercial/SagittaDB-Enterprise-v{COMMERCIAL_VERSION}.zip.sig.json",
            f"dist-commercial/SagittaDB-Enterprise-v{COMMERCIAL_VERSION}.zip.asc",
            f"dist-commercial/SagittaDB-Enterprise-v{COMMERCIAL_VERSION}.zip.sig",
        ],
        "path": "/commercial",
    },
    {
        "key": "sbom_materials",
        "label": "SBOM 与签名材料",
        "name": "SBOM 与签名材料",
        "blocking": False,
        "kind": "glob",
        "paths": [
            "dist-commercial/sbom/*.cyclonedx.json",
            "dist-commercial/sbom/*.cyclonedx.json.sha256",
            "dist-commercial/sbom/*.cyclonedx.json.bundle",
        ],
        "path": "/commercial",
    },
]

ENGINE_MATRIX: list[dict[str, Any]] = [
    {
        "db_type": "mysql",
        "label": "MySQL",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": True,
            "monitor": True,
            "session": True,
            "explain": True,
            "kill_session": True,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "postgres",
        "label": "PostgreSQL",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": True,
            "monitor": True,
            "session": True,
            "explain": True,
            "kill_session": False,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "tidb",
        "label": "TiDB",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": True,
            "monitor": True,
            "session": True,
            "explain": True,
            "kill_session": False,
        },
        "validation_required": "按 MySQL 兼容链路验收",
    },
    {
        "db_type": "starrocks",
        "label": "StarRocks",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": True,
            "monitor": True,
            "session": True,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "clickhouse",
        "label": "ClickHouse",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "mongo",
        "label": "MongoDB",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": True,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "redis",
        "label": "Redis",
        "support_level": "ga",
        "support_label": "GA 正式支持",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": False,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "标准交付验收",
    },
    {
        "db_type": "oracle",
        "label": "Oracle",
        "support_level": "validated_minimal",
        "support_label": "客户验证后交付",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": False,
            "monitor": True,
            "session": True,
            "explain": True,
            "kill_session": False,
        },
        "validation_required": "必须在客户同构环境验证驱动模式、权限和诊断降级链路",
    },
    {
        "db_type": "mssql",
        "label": "MSSQL",
        "support_level": "validated_minimal",
        "support_label": "客户验证后交付",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": False,
            "monitor": True,
            "session": True,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "必须在客户同构环境验证连接、元数据和执行链路",
    },
    {
        "db_type": "doris",
        "label": "Doris",
        "support_level": "validated_minimal",
        "support_label": "客户验证后交付",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": True,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "必须在客户 FE MySQL 协议版本验证",
    },
    {
        "db_type": "elasticsearch",
        "label": "Elasticsearch",
        "support_level": "validated_minimal",
        "support_label": "客户验证后交付",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": False,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "必须验证目标版本 SQL API 兼容性",
    },
    {
        "db_type": "opensearch",
        "label": "OpenSearch",
        "support_level": "validated_minimal",
        "support_label": "客户验证后交付",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": False,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "必须验证目标版本 SQL API 兼容性",
    },
    {
        "db_type": "cassandra",
        "label": "Cassandra/ScyllaDB",
        "support_level": "read_only_metadata",
        "support_label": "只读/元数据",
        "capabilities": {
            "connection": True,
            "schema": True,
            "query": True,
            "workflow": False,
            "archive": False,
            "monitor": True,
            "session": False,
            "explain": False,
            "kill_session": False,
        },
        "validation_required": "只承诺元数据和只读 SELECT；DDL/DML/BATCH 不纳入标准交付",
    },
]


def _now() -> datetime:
    return datetime.now(UTC)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if any(token in key.lower() for token in ("password", "secret", "token", "key", "url"))
            else _redact(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and any(token in value.lower() for token in ("password=", "token=", "secret=")):
        return "***REDACTED***"
    return value


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


class CommercialOpsService:
    @staticmethod
    async def _scalar_count(db: AsyncSession, model: Any, *where: Any) -> int:
        stmt = select(func.count()).select_from(model)
        if where:
            stmt = stmt.where(*where)
        return int((await db.execute(stmt)).scalar_one() or 0)

    @staticmethod
    def _project_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "backend").exists() and (parent / "frontend").exists():
                return parent
        return Path.cwd()

    @staticmethod
    def _preflight_detail(ok: bool, ready: list[str], missing: list[str], non_executable: list[str]) -> str:
        if ok:
            return "已就绪：" + "、".join(ready)
        parts = []
        if missing:
            parts.append("未找到：" + "、".join(missing))
        if non_executable:
            parts.append("不可执行：" + "、".join(non_executable))
        return "；".join(parts) or "未满足交付自检要求"

    @staticmethod
    def _evaluate_preflight_definition(root: Path, definition: dict[str, Any]) -> dict[str, Any]:
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

        return {
            "key": definition["key"],
            "label": definition["label"],
            "name": definition["name"],
            "ok": ok,
            "blocking": bool(definition["blocking"]),
            "detail": CommercialOpsService._preflight_detail(ok, ready, missing, non_executable),
            "path": definition["path"],
        }

    @staticmethod
    def delivery_preflight(root: Path | None = None) -> dict[str, Any]:
        base = root or CommercialOpsService._project_root()
        checks = [
            CommercialOpsService._evaluate_preflight_definition(base, definition)
            for definition in DELIVERY_PREFLIGHT_DEFINITIONS
        ]
        failed_blockers = [item for item in checks if item["blocking"] and not item["ok"]]
        failed_optional = [item for item in checks if not item["blocking"] and not item["ok"]]
        return {
            "root": str(base),
            "status": "blocked" if failed_blockers else "needs_configuration" if failed_optional else "ready",
            "checks": checks,
        }

    @staticmethod
    async def usage_payload(db: AsyncSession) -> dict[str, Any]:
        if not hasattr(db, "execute"):
            return {"active_users": 0, "active_instances": 0, "db_type_distribution": {}}
        db_type_rows = (
            await db.execute(
                select(Instance.db_type, func.count())
                .where(Instance.is_active.is_(True))
                .group_by(Instance.db_type)
            )
        ).all()
        return {
            "active_users": await CommercialOpsService._scalar_count(
                db, Users, Users.is_active.is_(True)
            ),
            "active_instances": await CommercialOpsService._scalar_count(
                db, Instance, Instance.is_active.is_(True)
            ),
            "db_type_distribution": {str(db_type): int(count) for db_type, count in db_type_rows},
        }

    @staticmethod
    async def commercial_readiness(db: AsyncSession, license_state: dict[str, Any] | None = None) -> dict[str, Any]:
        license_state = license_state or await LicenseService.status(db)
        checks = [
            {
                "key": "license",
                "label": "License 可用",
                "ok": license_state.get("status") in {"trial", "licensed"},
                "blocking": True,
                "detail": license_state.get("reason") or "未获取到授权状态",
                "path": "/system/license",
            },
            {
                "key": "license_activation_ready",
                "label": "正式授权材料",
                "ok": bool(license_state.get("activation_customer_id") and license_state.get("activation_deployment_fingerprint")),
                "blocking": False,
                "detail": "客户 ID 与正式激活部署指纹可用于授权中心签发",
                "path": "/system/license",
            },
            {
                "key": "instance",
                "label": "至少一个实例",
                "ok": await CommercialOpsService._scalar_count(db, Instance, Instance.is_active.is_(True)) > 0,
                "blocking": True,
                "detail": "需要接入客户同构测试实例",
                "path": "/instance",
            },
            {
                "key": "governance",
                "label": "治理配置",
                "ok": (
                    await CommercialOpsService._scalar_count(db, ResourceGroup) > 0
                    and await CommercialOpsService._scalar_count(db, UserGroup) > 0
                    and await CommercialOpsService._scalar_count(db, ApprovalFlow) > 0
                ),
                "blocking": True,
                "detail": "资源组、用户组和审批流均需完成",
                "path": "/system/groups",
            },
            {
                "key": "notification",
                "label": "通知链路",
                "ok": await CommercialOpsService._notification_configured(db),
                "blocking": False,
                "detail": "建议至少配置邮件、飞书、钉钉或企微中的一种",
                "path": "/system/config",
            },
            {
                "key": "acceptance",
                "label": "交付验收",
                "ok": await CommercialOpsService._scalar_count(db, DeliveryAcceptanceRun) > 0,
                "blocking": False,
                "detail": "建议生成一次客户现场验收报告",
                "path": "/commercial",
            },
        ]
        delivery_preflight = CommercialOpsService.delivery_preflight()
        checks.extend(
            {
                "key": f"delivery_{item['key']}",
                "label": item["label"],
                "ok": item["ok"],
                "blocking": item["blocking"],
                "detail": item["detail"],
                "path": item["path"],
            }
            for item in delivery_preflight["checks"]
        )
        failed_blockers = [item for item in checks if item["blocking"] and not item["ok"]]
        failed_optional = [item for item in checks if not item["blocking"] and not item["ok"]]
        if failed_blockers:
            status = "blocked"
            conclusion = "阻塞"
            summary = "核心交付条件未完成，暂不建议进入商业推广或客户验收。"
        elif failed_optional:
            status = "needs_configuration"
            conclusion = "需补配置"
            summary = "核心链路已具备，建议补齐通知、正式授权材料或验收报告后推广。"
        else:
            status = "ready"
            conclusion = "可推广"
            summary = "试用、授权、实例治理和验收材料已形成闭环。"
        return {
            "status": status,
            "conclusion": conclusion,
            "summary": summary,
            "score": round(sum(1 for item in checks if item["ok"]) / len(checks) * 100),
            "checks": checks,
            "action_items": [item for item in checks if not item["ok"]],
        }

    @staticmethod
    async def runtime_payload(db: AsyncSession, license_source: str = "") -> dict[str, Any]:
        if not hasattr(db, "execute"):
            failed_collects = 0
        else:
            failed_collects = await CommercialOpsService._scalar_count(
                db, MonitorCollectConfig, MonitorCollectConfig.last_collect_status == "failed"
            )
        return {
            "version": "2.1.4",
            "app_env": settings.APP_ENV,
            "deployment_mode": "commercial" if settings.SAGITTADB_COMMERCIAL_BUILD else "standard",
            "license_source": license_source,
            "health": "warning" if failed_collects else "ok",
            "failed_monitor_collect_configs": failed_collects,
        }

    @staticmethod
    async def _notification_configured(db: AsyncSession) -> bool:
        for key in ("ding_enabled", "wecom_enabled", "feishu_enabled"):
            if (await SystemConfigService.get_value(db, key)).lower() == "true":
                return True
        return bool(await SystemConfigService.get_value(db, "mail_host"))

    @staticmethod
    async def onboarding_status(db: AsyncSession) -> dict[str, Any]:
        raw = await SystemConfigService.get_value(db, "commercial_onboarding_completed_steps")
        try:
            completed = set(json.loads(raw or "[]"))
        except json.JSONDecodeError:
            completed = set()
        auth_enabled = False
        for key in (
            "ldap_enabled",
            "cas_enabled",
            "ding_login_enabled",
            "feishu_login_enabled",
            "wecom_login_enabled",
        ):
            if (await SystemConfigService.get_value(db, key)).lower() == "true":
                auth_enabled = True
                break
        notification_enabled = await CommercialOpsService._notification_configured(db)

        system_hints = {
            "branding": bool(await SystemConfigService.get_value(db, "platform_name")),
            "license": (await LicenseService.status(db)).get("status") == "licensed",
            "auth": auth_enabled,
            "notification": notification_enabled,
            "first_instance": await CommercialOpsService._scalar_count(db, Instance) > 0,
            "governance": (
                await CommercialOpsService._scalar_count(db, ResourceGroup) > 0
                and await CommercialOpsService._scalar_count(db, UserGroup) > 0
                and await CommercialOpsService._scalar_count(db, ApprovalFlow) > 0
            ),
            "acceptance": await CommercialOpsService._scalar_count(db, DeliveryAcceptanceRun) > 0,
        }
        items = []
        for step in ONBOARDING_STEPS:
            key = step["key"]
            done = key in completed or bool(system_hints.get(key))
            reason = {
                "branding": "已配置平台品牌" if system_hints.get(key) else "请确认平台名称、Logo 与客户现场展示口径",
                "license": "已完成正式授权" if system_hints.get(key) else "试用可继续，但转正式前需完成在线或离线授权",
                "auth": "已配置企业认证入口" if system_hints.get(key) else "建议启用 LDAP、CAS、OIDC 或企业应用登录",
                "notification": "已配置通知渠道" if system_hints.get(key) else "建议至少打通邮件、飞书、钉钉或企微中的一种",
                "first_instance": "已接入数据库实例" if system_hints.get(key) else "请接入一个生产同构测试实例",
                "governance": "治理对象已配置" if system_hints.get(key) else "请完成资源组、用户组和审批流配置",
                "acceptance": "已生成验收报告" if system_hints.get(key) else "建议生成 Markdown/JSON 验收报告留档",
            }.get(key, "")
            items.append({
                **step,
                "completed": done,
                "auto_detected": bool(system_hints.get(key)),
                "status": "done" if done else "todo",
                "reason": reason,
            })
        return {
            "steps": items,
            "completed_count": sum(1 for item in items if item["completed"]),
            "total": len(items),
            "is_complete": all(item["completed"] for item in items),
        }

    @staticmethod
    async def complete_onboarding_step(db: AsyncSession, step: str) -> dict[str, Any]:
        keys = {item["key"] for item in ONBOARDING_STEPS}
        if step not in keys:
            raise ValueError("未知实施步骤")
        raw = await SystemConfigService.get_value(db, "commercial_onboarding_completed_steps")
        try:
            completed = set(json.loads(raw or "[]"))
        except json.JSONDecodeError:
            completed = set()
        completed.add(step)
        item = (
            await db.execute(
                select(SystemConfig).where(SystemConfig.config_key == "commercial_onboarding_completed_steps")
            )
        ).scalar_one_or_none()
        value = json.dumps(sorted(completed), ensure_ascii=False)
        if item:
            item.config_value = value
            item.is_encrypted = False
        else:
            db.add(
                SystemConfig(
                    config_key="commercial_onboarding_completed_steps",
                    config_value=value,
                    is_encrypted=False,
                    description="商业化实施向导已完成步骤",
                    group="basic",
                )
            )
        await db.commit()
        return await CommercialOpsService.onboarding_status(db)

    @staticmethod
    async def create_acceptance_run(
        db: AsyncSession,
        user: dict,
        options: dict[str, Any],
    ) -> DeliveryAcceptanceRun:
        checks: list[dict[str, Any]] = []

        async def add(
            name: str,
            ok: bool,
            detail: str,
            skipped: bool = False,
            required: bool = True,
        ) -> None:
            checks.append({
                "name": name,
                "ok": ok,
                "detail": detail,
                "skipped": skipped,
                "required": required,
            })

        await add("健康检查", True, "后端服务可访问")
        license_state = await LicenseService.status(db)
        await add("License 状态", license_state["status"] in {"trial", "licensed"}, license_state["reason"])
        await add(
            "正式授权材料",
            bool(license_state.get("activation_customer_id") and license_state.get("activation_deployment_fingerprint")),
            f"customer_id={license_state.get('activation_customer_id') or '-'}",
        )
        branding = await SystemConfigService.get_branding(db)
        await add("品牌配置", bool(branding.get("platform_name")), branding.get("platform_name") or "未配置")
        await add("用户数量", await CommercialOpsService._scalar_count(db, Users) > 0, "已创建用户")
        await add("实例数量", await CommercialOpsService._scalar_count(db, Instance) > 0, "已创建实例")
        await add("资源组", await CommercialOpsService._scalar_count(db, ResourceGroup) > 0, "已创建资源组")
        await add("用户组", await CommercialOpsService._scalar_count(db, UserGroup) > 0, "已创建用户组")
        await add("审批流", await CommercialOpsService._scalar_count(db, ApprovalFlow) > 0, "已创建审批流")
        await add("通知链路", await CommercialOpsService._notification_configured(db), "至少一个通知渠道已配置")
        await add("SQL 工单链路", await CommercialOpsService._scalar_count(db, SqlWorkflow) > 0, "已存在 SQL 工单记录")
        await add("查询权限链路", await CommercialOpsService._scalar_count(db, QueryPrivilegeApply) > 0, "已存在查询权限申请记录")
        await add("在线查询链路", await CommercialOpsService._scalar_count(db, QueryLog) > 0, "已存在在线查询记录")
        await add("数据归档链路", await CommercialOpsService._scalar_count(db, ArchiveJob) > 0, "已存在归档作业记录")
        await add(
            "监控采集",
            await CommercialOpsService._scalar_count(db, MonitorMetricSnapshot) > 0,
            "已存在监控指标快照",
        )
        await add("审计日志", await CommercialOpsService._scalar_count(db, OperationLog) > 0, "审计日志可查询")
        for item in CommercialOpsService.delivery_preflight()["checks"]:
            await add(
                item["name"],
                bool(item["ok"]),
                str(item["detail"]),
                required=bool(item["blocking"]),
            )

        instance_id = options.get("instance_id")
        db_name = str(options.get("db_name") or "").strip()
        if instance_id:
            inst = (
                await db.execute(select(Instance).where(Instance.id == int(instance_id)))
            ).scalar_one_or_none()
            await add("指定实例", bool(inst), f"instance_id={instance_id}")
            if inst and db_name:
                registered = (
                    await db.execute(
                        select(InstanceDatabase).where(
                            InstanceDatabase.instance_id == inst.id,
                            InstanceDatabase.db_name == db_name,
                        )
                    )
                ).scalar_one_or_none()
                await add("指定数据库注册", bool(registered), db_name)
        else:
            await add("实例链路检查", True, "未选择实例，已跳过", skipped=True)

        failed = [
            item
            for item in checks
            if item.get("required", True) and not item["ok"] and not item["skipped"]
        ]
        warnings = [
            item
            for item in checks
            if not item.get("required", True) and not item["ok"] and not item["skipped"]
        ]
        readiness = await CommercialOpsService.commercial_readiness(db, license_state)
        if failed:
            readiness["status"] = "blocked"
            readiness["conclusion"] = "阻塞"
            readiness["summary"] = "验收检查存在失败项，请补齐后再进入客户推广或正式验收。"
        elif warnings:
            readiness["status"] = "needs_configuration"
            readiness["conclusion"] = "需补配置"
            readiness["summary"] = "核心链路可验收，建议补齐发布签名、SBOM 或客户包材料后再推广。"
        report = {
            "project": LICENSE_PROJECT_NAME,
            "project_code": LICENSE_PROJECT_CODE,
            "generated_at": _now().isoformat(),
            "generated_by": user.get("username", ""),
            "status": "failed" if failed else "success",
            "readiness": readiness,
            "summary": {
                "passed": sum(1 for item in checks if item["ok"] and not item["skipped"]),
                "failed": len(failed),
                "warnings": len(warnings),
                "skipped": sum(1 for item in checks if item["skipped"]),
            },
            "checks": checks,
            "options": options,
        }
        markdown = CommercialOpsService.acceptance_markdown(report)
        run = DeliveryAcceptanceRun(
            status=report["status"],
            options=options,
            report_json=report,
            report_markdown=markdown,
            created_by=user.get("username", ""),
            completed_at=_now(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    @staticmethod
    def acceptance_markdown(report: dict[str, Any]) -> str:
        lines = [
            "# SagittaDB 商业交付验收报告",
            "",
            f"- 项目：{report.get('project')}（{report.get('project_code')}）",
            f"- 生成时间：{report.get('generated_at')}",
            f"- 生成人：{report.get('generated_by') or '-'}",
            f"- 状态：{report.get('status')}",
            f"- 推广结论：{report.get('readiness', {}).get('conclusion', '-')}",
            f"- 结论说明：{report.get('readiness', {}).get('summary', '-')}",
            "",
            "## 汇总",
            "",
            *_markdown_table(
                ["通过", "失败", "需补配置", "跳过"],
                [[
                    report.get("summary", {}).get("passed", 0),
                    report.get("summary", {}).get("failed", 0),
                    report.get("summary", {}).get("warnings", 0),
                    report.get("summary", {}).get("skipped", 0),
                ]],
            ),
            "",
            "## 检查项",
            "",
            *_markdown_table(
                ["结果", "检查项", "说明"],
                [
                    [
                        "SKIP"
                        if item.get("skipped")
                        else ("PASS" if item.get("ok") else ("FAIL" if item.get("required", True) else "WARN")),
                        item.get("name", ""),
                        item.get("detail", ""),
                    ]
                    for item in report.get("checks", [])
                ],
            ),
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def run_to_dict(run: DeliveryAcceptanceRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "status": run.status,
            "options": run.options or {},
            "report_json": run.report_json or {},
            "created_by": run.created_by,
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    @staticmethod
    async def create_diagnostic_bundle(db: AsyncSession, user: dict) -> DiagnosticBundle:
        latest_license = await LicenseService.status(db)
        alembic_version = ""
        try:
            alembic_version = str(
                (await db.execute(text("select version_num from alembic_version limit 1"))).scalar_one_or_none()
                or ""
            )
        except Exception:
            alembic_version = "unknown"
        recent_errors = (
            await db.execute(
                select(OperationLog)
                .where(OperationLog.result == "fail")
                .order_by(OperationLog.created_at.desc())
                .limit(20)
            )
        ).scalars().all()
        failed_notifications = (
            await db.execute(
                select(NotificationDeliveryLog)
                .where(NotificationDeliveryLog.status == "failed")
                .order_by(NotificationDeliveryLog.created_at.desc())
                .limit(20)
            )
        ).scalars().all()
        failed_collects = (
            await db.execute(
                select(MonitorCollectConfig)
                .where(MonitorCollectConfig.last_collect_status == "failed")
                .limit(50)
            )
        ).scalars().all()
        bundle = _redact(
            {
                "generated_at": _now().isoformat(),
                "generated_by": user.get("username", ""),
                "version": "2.1.4",
                "app_env": settings.APP_ENV,
                "alembic_version": alembic_version,
                "license": latest_license,
                "counts": {
                    "users": await CommercialOpsService._scalar_count(db, Users),
                    "active_users": await CommercialOpsService._scalar_count(db, Users, Users.is_active.is_(True)),
                    "instances": await CommercialOpsService._scalar_count(db, Instance),
                    "active_instances": await CommercialOpsService._scalar_count(db, Instance, Instance.is_active.is_(True)),
                    "query_logs": await CommercialOpsService._scalar_count(db, QueryLog),
                    "audit_logs": await CommercialOpsService._scalar_count(db, OperationLog),
                    "monitor_snapshots": await CommercialOpsService._scalar_count(db, MonitorMetricSnapshot),
                },
                "recent_errors": [
                    {
                        "id": item.id,
                        "username": item.username,
                        "module": item.module,
                        "action": item.action,
                        "detail": item.detail,
                        "created_at": item.created_at.isoformat() if item.created_at else "",
                    }
                    for item in recent_errors
                ],
                "failed_notifications": [
                    {
                        "id": item.id,
                        "event_type": item.event_type,
                        "channel": item.channel,
                        "error": item.error,
                        "created_at": item.created_at.isoformat() if item.created_at else "",
                    }
                    for item in failed_notifications
                ],
                "failed_monitor_collects": [
                    {
                        "instance_id": item.instance_id,
                        "last_collect_error": item.last_collect_error,
                        "last_metric_collect_at": item.last_metric_collect_at.isoformat()
                        if item.last_metric_collect_at
                        else None,
                    }
                    for item in failed_collects
                ],
                "celery": {"status": "not_checked", "reason": "诊断包第一版不直接连接 broker"},
            }
        )
        record = DiagnosticBundle(
            status="success",
            bundle_json=bundle,
            created_by=user.get("username", ""),
            completed_at=_now(),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def compliance_report(db: AsyncSession, report_type: str) -> dict[str, Any]:
        now = _now()
        start = now - timedelta(days=30)
        if report_type == "query_export":
            rows = (
                await db.execute(
                    select(QueryLog)
                    .where(QueryLog.operation_type == "export", QueryLog.created_at >= start)
                    .order_by(QueryLog.created_at.desc())
                    .limit(500)
                )
            ).scalars().all()
            items = [
                {
                    "id": row.id,
                    "username": row.username,
                    "instance_name": row.instance_name,
                    "db_name": row.db_name,
                    "export_format": row.export_format,
                    "masking": row.masking,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                for row in rows
            ]
        elif report_type == "license_operations":
            rows = (
                await db.execute(
                    select(OperationLog)
                    .where(OperationLog.action.ilike("%license%"), OperationLog.created_at >= start)
                    .order_by(OperationLog.created_at.desc())
                    .limit(500)
                )
            ).scalars().all()
            items = [CommercialOpsService.operation_log_item(row) for row in rows]
        elif report_type == "permission_changes":
            rows = (
                await db.execute(
                    select(OperationLog)
                    .where(
                        OperationLog.created_at >= start,
                        OperationLog.module.in_(["user", "system", "query", "monitor"]),
                    )
                    .order_by(OperationLog.created_at.desc())
                    .limit(500)
                )
            ).scalars().all()
            active_privileges = await CommercialOpsService._scalar_count(
                db, QueryPrivilege, QueryPrivilege.is_deleted == 0
            )
            items = [CommercialOpsService.operation_log_item(row) for row in rows]
            items.insert(0, {"metric": "active_query_privileges", "value": active_privileges})
        elif report_type == "high_risk_operations":
            rows = (
                await db.execute(
                    select(OperationLog)
                    .where(
                        OperationLog.created_at >= start,
                        OperationLog.action.ilike("%kill%")
                        | OperationLog.action.ilike("%delete%")
                        | OperationLog.action.ilike("%reject%")
                        | OperationLog.action.ilike("%revoke%")
                        | OperationLog.detail.ilike("%DROP%")
                        | OperationLog.detail.ilike("%TRUNCATE%"),
                    )
                    .order_by(OperationLog.created_at.desc())
                    .limit(500)
                )
            ).scalars().all()
            items = [CommercialOpsService.operation_log_item(row) for row in rows]
        else:
            raise ValueError("不支持的合规报表类型")

        report = {
            "report_type": report_type,
            "generated_at": now.isoformat(),
            "period": {"start": start.isoformat(), "end": now.isoformat()},
            "total": len(items),
            "items": items,
        }
        report["markdown"] = CommercialOpsService.compliance_markdown(report)
        return report

    @staticmethod
    def operation_log_item(row: OperationLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "username": row.username,
            "module": row.module,
            "action": row.action,
            "result": row.result,
            "detail": row.detail,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }

    @staticmethod
    def compliance_markdown(report: dict[str, Any]) -> str:
        lines = [
            f"# SagittaDB 合规报表：{report['report_type']}",
            "",
            f"- 生成时间：{report['generated_at']}",
            f"- 统计周期：{report['period']['start']} 至 {report['period']['end']}",
            f"- 记录数：{report['total']}",
            "",
            "```json",
            json.dumps(report.get("items", []), ensure_ascii=False, indent=2),
            "```",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def build_rows_file(
        rows: list[dict[str, Any]],
        export_format: str,
        filename_prefix: str,
    ) -> tuple[bytes, str, str]:
        headers = sorted({key for row in rows for key in row}) or ["empty"]
        if export_format == "json":
            return (
                json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json; charset=utf-8",
                f"{filename_prefix}.json",
            )
        if export_format == "csv":
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
            return (
                output.getvalue().encode("utf-8-sig"),
                "text/csv; charset=utf-8",
                f"{filename_prefix}.csv",
            )
        wb = Workbook()
        ws = wb.active
        ws.title = "Export"
        ws.append(headers)
        for row in rows:
            ws.append([row.get(key, "") for key in headers])
        content = BytesIO()
        wb.save(content)
        return (
            content.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{filename_prefix}.xlsx",
        )

    @staticmethod
    def engine_matrix() -> dict[str, Any]:
        return {
            "levels": {
                "ga": "GA 正式支持",
                "validated_minimal": "客户验证后交付",
                "read_only_metadata": "只读/元数据",
                "experimental": "实验性",
                "backlog": "暂不承诺",
            },
            "capability_labels": {
                "connection": "连接测试",
                "schema": "数据字典",
                "query": "在线查询",
                "workflow": "SQL 工单",
                "archive": "归档",
                "monitor": "观测",
                "session": "会话诊断",
                "explain": "执行计划",
                "kill_session": "Kill 会话",
            },
            "items": ENGINE_MATRIX,
        }

    @staticmethod
    async def support_about(db: AsyncSession) -> dict[str, Any]:
        license_status = await LicenseService.status(db)
        usage = await CommercialOpsService.usage_payload(db)
        runtime = await CommercialOpsService.runtime_payload(
            db, str(license_status.get("source") or "")
        )
        readiness = await CommercialOpsService.commercial_readiness(db, license_status)
        return {
            "version": "2.1.4",
            "project": LICENSE_PROJECT_NAME,
            "project_code": LICENSE_PROJECT_CODE,
            "deployment_mode": "commercial" if settings.SAGITTADB_COMMERCIAL_BUILD else "standard",
            "app_env": settings.APP_ENV,
            "deployment_fingerprint": license_status.get("deployment_fingerprint") or "",
            "license": license_status,
            "usage": usage,
            "runtime": runtime,
            "readiness": readiness,
            "docs": [
                {"label": "用户使用手册", "path": "/docs/user_manual.md"},
                {"label": "运维管理手册", "path": "/docs/operations_guide.md"},
                {"label": "商业交付说明", "path": "/docs/public_commercial_delivery.md"},
            ],
            "support": {
                "email": "support@loveai.asia",
                "license_server": settings.LICENSE_SERVER_URL or "https://license.loveai.asia",
            },
        }

    @staticmethod
    async def retention_policy(db: AsyncSession) -> dict[str, Any]:
        items = []
        for key, default_days in RETENTION_DEFAULTS.items():
            raw = await SystemConfigService.get_value(db, f"commercial_retention_{key}_days")
            try:
                days = max(1, int(raw or default_days))
            except (TypeError, ValueError):
                days = default_days
            items.append(
                {
                    "key": key,
                    "label": RETENTION_LABELS[key],
                    "days": days,
                    "default_days": default_days,
                }
            )
        return {"items": items}

    @staticmethod
    async def update_retention_policy(db: AsyncSession, values: dict[str, int]) -> dict[str, Any]:
        for key, days in values.items():
            if key not in RETENTION_DEFAULTS:
                continue
            safe_days = max(1, min(int(days), 3650))
            config_key = f"commercial_retention_{key}_days"
            item = (
                await db.execute(select(SystemConfig).where(SystemConfig.config_key == config_key))
            ).scalar_one_or_none()
            if item:
                item.config_value = str(safe_days)
                item.is_encrypted = False
            else:
                db.add(
                    SystemConfig(
                        config_key=config_key,
                        config_value=str(safe_days),
                        is_encrypted=False,
                        description=f"{RETENTION_LABELS[key]}保留天数",
                        group="basic",
                    )
                )
        await db.commit()
        return await CommercialOpsService.retention_policy(db)

    @staticmethod
    async def cleanup_retention_category(db: AsyncSession, category: str) -> dict[str, Any]:
        if category not in RETENTION_DEFAULTS:
            raise ValueError("不支持的保留策略类别")
        policy = await CommercialOpsService.retention_policy(db)
        days_by_key = {item["key"]: item["days"] for item in policy["items"]}
        cutoff = _now() - timedelta(days=days_by_key.get(category, RETENTION_DEFAULTS[category]))
        if category == "operation_audit":
            stmt = delete(OperationLog).where(OperationLog.created_at < cutoff)
        elif category == "query_history":
            stmt = delete(QueryLog).where(QueryLog.created_at < cutoff)
        elif category == "notification_log":
            stmt = delete(NotificationDeliveryLog).where(NotificationDeliveryLog.created_at < cutoff)
        else:
            stmt = delete(MonitorMetricSnapshot).where(MonitorMetricSnapshot.created_at < cutoff)
        result = await db.execute(stmt)
        await db.commit()
        return {
            "category": category,
            "label": RETENTION_LABELS[category],
            "cutoff": cutoff.isoformat(),
            "deleted": int(result.rowcount or 0),
        }
