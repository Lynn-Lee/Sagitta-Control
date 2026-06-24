"""商业化运营、交付验收、合规报表和支持矩阵服务。"""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, date, datetime, timedelta
from fnmatch import fnmatch
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.approval_flow import ApprovalFlow, ApprovalFlowNode
from app.models.archive import ArchiveJob, ArchiveJobStatus
from app.models.instance import Instance, InstanceDatabase
from app.models.monitor import MonitorCollectConfig, MonitorMetricSnapshot
from app.models.query import QueryLog, QueryPrivilege, QueryPrivilegeApply
from app.models.role import UserGroup, group_resource_group, user_group_member
from app.models.system import (
    DeliveryAcceptanceRun,
    DiagnosticBundle,
    NotificationDeliveryLog,
    OperationLog,
    SystemConfig,
)
from app.models.user import ResourceGroup, Users, instance_resource_group
from app.models.workflow import SqlWorkflow, SqlWorkflowContent, WorkflowStatus
from app.services.commercial_ops_metadata import (
    COMMERCIAL_VERSION,
    DELIVERY_MANIFEST_PATH,
    DELIVERY_PREFLIGHT_DEFINITIONS,
    DEMO_APPROVAL_FLOW_NAME,
    DEMO_MARKER,
    DEMO_RESOURCE_GROUP_NAME,
    DEMO_USER_GROUP_NAME,
    ENGINE_MATRIX,
    ONBOARDING_STEPS,
    RETENTION_DEFAULTS,
    RETENTION_LABELS,
)
from app.services.license import (
    LICENSE_PROJECT_CODE,
    LICENSE_PROJECT_NAME,
    LicenseService,
)
from app.services.role import RoleService
from app.services.system_config import SystemConfigService


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


ONBOARDING_STEP_GUIDANCE: dict[str, dict[str, Any]] = {
    "branding": {
        "category": "试用准备",
        "required": False,
        "action_label": "确认品牌",
        "suggested_action": "确认平台名称、Logo、登录页和客户现场展示口径一致。",
        "fix_hint": "初始化试用环境会补齐默认平台名称；正式客户仍建议按现场品牌复核。",
        "quick_action": "trial_bootstrap",
        "can_auto_fix": True,
        "done_evidence": "已检测到平台名称配置",
        "todo_evidence": "未检测到平台名称配置",
    },
    "license": {
        "category": "上线前置",
        "required": True,
        "action_label": "处理授权",
        "suggested_action": "导入正式 License，或复制正式部署指纹到授权中心签发。",
        "fix_hint": "试用阶段可继续推进；正式上线前必须完成授权激活并复核客户 ID。",
        "quick_action": "navigate",
        "can_auto_fix": False,
        "done_evidence": "已检测到正式授权",
        "todo_evidence": "当前仍为试用或授权未完成",
    },
    "auth": {
        "category": "上线前置",
        "required": False,
        "action_label": "配置认证",
        "suggested_action": "启用 LDAP、CAS、OIDC 或企业应用登录，并用测试账号完成一次登录验证。",
        "fix_hint": "没有企业认证也可试用；客户正式推广前建议至少接入一种统一身份入口。",
        "quick_action": "navigate",
        "can_auto_fix": False,
        "done_evidence": "已检测到企业认证入口",
        "todo_evidence": "未检测到企业认证入口",
    },
    "notification": {
        "category": "上线前置",
        "required": False,
        "action_label": "打通通知",
        "suggested_action": "配置邮件、飞书、钉钉或企微，并执行一次连通性测试。",
        "fix_hint": "通知未配置不会阻塞试用，但会影响审批、告警和客户验收闭环。",
        "quick_action": "navigate",
        "can_auto_fix": False,
        "done_evidence": "已检测到至少一种通知渠道",
        "todo_evidence": "未检测到可用通知渠道",
    },
    "first_instance": {
        "category": "首个实例",
        "required": True,
        "action_label": "接入实例",
        "suggested_action": "接入一个客户同构测试实例，完成连接测试、资源组归属和基础权限校验。",
        "fix_hint": "系统不会伪造活跃实例；没有实例时只能生成治理模板和空验收框架。",
        "quick_action": "navigate",
        "can_auto_fix": False,
        "done_evidence": "已检测到活跃实例",
        "todo_evidence": "未检测到活跃实例",
    },
    "governance": {
        "category": "治理模板",
        "required": True,
        "action_label": "初始化模板",
        "suggested_action": "确认资源组、用户组和审批流已经覆盖首个实例和试用管理员。",
        "fix_hint": "初始化试用环境会幂等创建商业试用资源组、团队和标准审批流。",
        "quick_action": "trial_bootstrap",
        "can_auto_fix": True,
        "done_evidence": "已检测到资源组、用户组和审批流",
        "todo_evidence": "资源组、用户组或审批流尚未齐备",
    },
    "acceptance": {
        "category": "验收留档",
        "required": False,
        "action_label": "生成报告",
        "suggested_action": "生成 Markdown/JSON 验收报告，记录实例、授权、治理、通知和交付材料状态。",
        "fix_hint": "初始化试用环境会尝试生成演示验收报告；正式客户建议指定实例和库名重新生成。",
        "quick_action": "generate_acceptance",
        "can_auto_fix": True,
        "done_evidence": "已检测到验收报告",
        "todo_evidence": "尚未生成验收报告",
    },
}


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
    def _load_delivery_manifest() -> dict[str, Any] | None:
        manifest_path = Path(os.getenv("COMMERCIAL_DELIVERY_MANIFEST") or DELIVERY_MANIFEST_PATH)
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if data.get("version") != COMMERCIAL_VERSION or not isinstance(data.get("materials"), list):
            return None
        return data

    @staticmethod
    def _manifest_materials(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not manifest:
            return {}
        materials: dict[str, dict[str, Any]] = {}
        for item in manifest.get("materials", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                materials[item["path"]] = item
        return materials

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
    def _evaluate_preflight_definition(
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

        manifest_materials = CommercialOpsService._manifest_materials(manifest)
        if not ok and manifest_materials:
            manifest_ready: list[str] = []
            manifest_missing: list[str] = []
            manifest_non_executable: list[str] = []
            if kind == "glob":
                for pattern in paths:
                    matches = sorted(path for path in manifest_materials if fnmatch(path, pattern))
                    if matches:
                        manifest_ready.extend(matches[:3])
                    else:
                        manifest_missing.append(pattern)
                ok = not manifest_missing
            elif kind == "all_executable":
                for relative in paths:
                    item = manifest_materials.get(relative)
                    if not item:
                        manifest_missing.append(relative)
                    elif not item.get("executable", False):
                        manifest_non_executable.append(relative)
                    else:
                        manifest_ready.append(relative)
                ok = not manifest_missing and not manifest_non_executable
            else:
                for relative in paths:
                    item = manifest_materials.get(relative)
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
            "detail": CommercialOpsService._preflight_detail(ok, ready, missing, non_executable),
            "path": definition["path"],
        }

    @staticmethod
    def delivery_preflight(
        root: Path | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = root or CommercialOpsService._project_root()
        if manifest is not None:
            manifest_data = manifest
        elif root is None:
            manifest_data = CommercialOpsService._load_delivery_manifest()
        else:
            manifest_data = None
        checks = [
            CommercialOpsService._evaluate_preflight_definition(base, definition, manifest_data)
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
            "version": COMMERCIAL_VERSION,
            "app_env": settings.APP_ENV,
            "deployment_mode": "commercial" if settings.SAGITTA_CONTROL_COMMERCIAL_BUILD else "standard",
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
        items = CommercialOpsService._build_onboarding_steps(completed, system_hints)
        next_actions = [item for item in items if not item["completed"]]
        risk_items = [item for item in next_actions if item["required"]]
        return {
            "steps": items,
            "completed_count": sum(1 for item in items if item["completed"]),
            "total": len(items),
            "is_complete": all(item["completed"] for item in items),
            "next_actions": next_actions,
            "risk_items": risk_items,
        }

    @staticmethod
    def _build_onboarding_steps(completed: set[str], system_hints: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for step in ONBOARDING_STEPS:
            key = step["key"]
            auto_detected = bool(system_hints.get(key))
            done = key in completed or auto_detected
            guidance = ONBOARDING_STEP_GUIDANCE.get(key, {})
            required = bool(guidance.get("required", False))
            reason = {
                "branding": "已配置平台品牌" if auto_detected else "请确认平台名称、Logo 与客户现场展示口径",
                "license": "已完成正式授权" if auto_detected else "试用可继续，但转正式前需完成在线或离线授权",
                "auth": "已配置企业认证入口" if auto_detected else "建议启用 LDAP、CAS、OIDC 或企业应用登录",
                "notification": "已配置通知渠道" if auto_detected else "建议至少打通邮件、飞书、钉钉或企微中的一种",
                "first_instance": "已接入数据库实例" if auto_detected else "请接入一个生产同构测试实例",
                "governance": "治理对象已配置" if auto_detected else "请完成资源组、用户组和审批流配置",
                "acceptance": "已生成验收报告" if auto_detected else "建议生成 Markdown/JSON 验收报告留档",
            }.get(key, "")
            items.append({
                **step,
                "category": guidance.get("category", "实施步骤"),
                "completed": done,
                "auto_detected": auto_detected,
                "status": "done" if done else "blocked" if required else "todo",
                "required": required,
                "priority": "blocking" if required else "recommended",
                "reason": reason,
                "evidence": guidance.get("done_evidence" if auto_detected else "todo_evidence", ""),
                "suggested_action": guidance.get("suggested_action", reason),
                "fix_hint": guidance.get("fix_hint", ""),
                "action_label": guidance.get("action_label", "去处理"),
                "quick_action": guidance.get("quick_action", "navigate"),
                "can_auto_fix": bool(guidance.get("can_auto_fix", False)),
                "detect_source": "自动检测" if auto_detected else "待配置",
            })
        return items

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
    async def _ensure_system_config(
        db: AsyncSession,
        key: str,
        value: str,
        description: str,
        group: str = "basic",
    ) -> tuple[bool, str]:
        item = (
            await db.execute(select(SystemConfig).where(SystemConfig.config_key == key))
        ).scalar_one_or_none()
        if item:
            if str(item.config_value or "").strip():
                return False, f"{key} 已存在，未覆盖"
            item.config_value = value
            item.is_encrypted = False
            item.description = item.description or description
            item.group = item.group or group
            return True, f"{key} 已补齐"
        db.add(
            SystemConfig(
                config_key=key,
                config_value=value,
                is_encrypted=False,
                description=description,
                group=group,
            )
        )
        return True, f"{key} 已创建"

    @staticmethod
    async def _association_exists(db: AsyncSession, table: Any, **values: int) -> bool:
        stmt = select(table)
        for key, value in values.items():
            stmt = stmt.where(getattr(table.c, key) == value)
        return (await db.execute(stmt.limit(1))).first() is not None

    @staticmethod
    async def _first_active_instance(db: AsyncSession) -> Instance | None:
        return (
            await db.execute(
                select(Instance)
                .where(Instance.is_active.is_(True))
                .order_by(Instance.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _first_actor(db: AsyncSession, user: dict[str, Any]) -> Users | None:
        user_id = user.get("id")
        if user_id:
            actor = (
                await db.execute(select(Users).where(Users.id == int(user_id)))
            ).scalar_one_or_none()
            if actor:
                return actor
        username = str(user.get("username") or "")
        if username:
            actor = (
                await db.execute(select(Users).where(Users.username == username))
            ).scalar_one_or_none()
            if actor:
                return actor
        return (
            await db.execute(
                select(Users)
                .where(Users.is_active.is_(True))
                .order_by(Users.is_superuser.desc(), Users.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def bootstrap_trial_environment(db: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
        """幂等初始化商业试用/演示环境。

        该流程只创建治理模板和可解释的样例记录；不会伪造活跃数据库实例或写入真实密码。
        如果客户现场已经接入活跃实例，则补充基于该实例的演示链路数据。
        """

        created: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []

        def record(changed: bool, detail: str) -> None:
            (updated if changed else skipped).append(detail)

        await RoleService.init_builtin_roles(db)
        skipped.append("内置角色和权限码已确认")

        actor = await CommercialOpsService._first_actor(db, user)
        actor_id = actor.id if actor else int(user.get("id") or 0)
        actor_username = (actor.username if actor else str(user.get("username") or "admin")) or "admin"
        actor_display = (actor.display_name if actor else actor_username) or actor_username

        changed, detail = await CommercialOpsService._ensure_system_config(
            db,
            "platform_name",
            "Sagitta Control",
            "平台名称",
        )
        record(changed, detail)

        rg = (
            await db.execute(
                select(ResourceGroup).where(ResourceGroup.group_name == DEMO_RESOURCE_GROUP_NAME)
            )
        ).scalar_one_or_none()
        if not rg:
            rg = ResourceGroup(
                group_name=DEMO_RESOURCE_GROUP_NAME,
                group_name_cn="商业试用资源组",
                is_active=True,
            )
            db.add(rg)
            await db.flush()
            created.append("商业试用资源组")
        elif not rg.is_active:
            rg.is_active = True
            updated.append("商业试用资源组已重新启用")
        else:
            skipped.append("商业试用资源组已存在")

        ug = (
            await db.execute(select(UserGroup).where(UserGroup.name == DEMO_USER_GROUP_NAME))
        ).scalar_one_or_none()
        if not ug:
            ug = UserGroup(
                name=DEMO_USER_GROUP_NAME,
                name_cn="商业试用团队",
                description="用于商业试用、销售演示和客户现场验收的默认团队",
                leader_id=actor_id or None,
                is_active=True,
            )
            db.add(ug)
            await db.flush()
            created.append("商业试用团队")
        else:
            changed_ug = False
            if not ug.is_active:
                ug.is_active = True
                changed_ug = True
            if actor_id and not ug.leader_id:
                ug.leader_id = actor_id
                changed_ug = True
            (updated if changed_ug else skipped).append(
                "商业试用团队已更新" if changed_ug else "商业试用团队已存在"
            )

        if not await CommercialOpsService._association_exists(
            db,
            group_resource_group,
            group_id=ug.id,
            resource_group_id=rg.id,
        ):
            await db.execute(
                group_resource_group.insert().values(group_id=ug.id, resource_group_id=rg.id)
            )
            created.append("商业试用团队已关联资源组")
        else:
            skipped.append("商业试用团队资源范围已存在")

        if actor_id and not await CommercialOpsService._association_exists(
            db,
            user_group_member,
            user_id=actor_id,
            group_id=ug.id,
        ):
            await db.execute(user_group_member.insert().values(user_id=actor_id, group_id=ug.id))
            created.append("当前管理员已加入商业试用团队")
        elif actor_id:
            skipped.append("当前管理员已在商业试用团队")

        flow = (
            await db.execute(
                select(ApprovalFlow)
                .where(ApprovalFlow.name == DEMO_APPROVAL_FLOW_NAME)
                .order_by(ApprovalFlow.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not flow:
            flow = ApprovalFlow(
                name=DEMO_APPROVAL_FLOW_NAME,
                description="商业试用默认审批流：任一具备 SQL 审核权限的人员可处理",
                is_active=True,
                created_by=actor_username,
                created_by_id=actor_id or None,
            )
            db.add(flow)
            await db.flush()
            db.add(
                ApprovalFlowNode(
                    flow_id=flow.id,
                    order=1,
                    node_name="DBA 审核",
                    approver_type="any_reviewer",
                    approver_ids="[]",
                )
            )
            created.append("商业试用标准审批流")
        elif not flow.is_active:
            flow.is_active = True
            updated.append("商业试用标准审批流已重新启用")
        else:
            skipped.append("商业试用标准审批流已存在")

        instance = await CommercialOpsService._first_active_instance(db)
        db_name = (instance.db_name if instance and instance.db_name else "demo") if instance else ""
        if instance:
            if not await CommercialOpsService._association_exists(
                db,
                instance_resource_group,
                instance_id=instance.id,
                resource_group_id=rg.id,
            ):
                await db.execute(
                    instance_resource_group.insert().values(
                        instance_id=instance.id,
                        resource_group_id=rg.id,
                    )
                )
                created.append(f"实例 {instance.instance_name} 已关联商业试用资源组")
            else:
                skipped.append(f"实例 {instance.instance_name} 已在商业试用资源组")

            if not (
                await db.execute(
                    select(SqlWorkflow)
                    .where(
                        SqlWorkflow.workflow_name == "商业试用 SQL 上线演示",
                        SqlWorkflow.engineer == actor_username,
                    )
                    .order_by(SqlWorkflow.id)
                    .limit(1)
                )
            ).scalar_one_or_none():
                workflow = SqlWorkflow(
                    workflow_name="商业试用 SQL 上线演示",
                    group_id=rg.id,
                    group_name=rg.group_name_cn or rg.group_name,
                    instance_id=instance.id,
                    db_name=db_name,
                    syntax_type=2,
                    is_backup=True,
                    engineer=actor_username,
                    engineer_display=actor_display,
                    engineer_id=actor_id,
                    status=WorkflowStatus.PENDING_REVIEW,
                    flow_id=flow.id,
                    audit_auth_groups=str(flow.id),
                )
                db.add(workflow)
                await db.flush()
                db.add(
                    SqlWorkflowContent(
                        workflow_id=workflow.id,
                        sql_content="UPDATE orders SET status = 'ARCHIVED' WHERE created_at < '2025-01-01';",
                        review_content=json.dumps(
                            {"source": DEMO_MARKER, "risk_level": "medium"},
                            ensure_ascii=False,
                        ),
                        risk_plan=json.dumps(
                            {"rollback": "使用备份表或 binlog 恢复受影响订单状态"},
                            ensure_ascii=False,
                        ),
                        risk_remark="商业试用样例，不会自动执行。",
                    )
                )
                created.append("SQL 工单演示记录")
            else:
                skipped.append("SQL 工单演示记录已存在")

            if not (
                await db.execute(
                    select(QueryPrivilegeApply)
                    .where(
                        QueryPrivilegeApply.title == "商业试用查询权限申请",
                        QueryPrivilegeApply.user_id == actor_id,
                    )
                    .order_by(QueryPrivilegeApply.id)
                    .limit(1)
                )
            ).scalar_one_or_none():
                db.add(
                    QueryPrivilegeApply(
                        title="商业试用查询权限申请",
                        user_id=actor_id,
                        instance_id=instance.id,
                        resource_group_id=rg.id,
                        group_id=rg.id,
                        scope_type="database",
                        db_name=db_name,
                        valid_date=date.today() + timedelta(days=30),
                        limit_num=100,
                        apply_reason="商业试用演示：研发申请临时查询订单库。",
                        risk_level="low",
                        risk_summary="只读查询，限制返回行数。",
                        status=0,
                        audit_auth_groups=str(flow.id),
                        flow_id=flow.id,
                    )
                )
                created.append("查询权限申请演示记录")
            else:
                skipped.append("查询权限申请演示记录已存在")

            if not (
                await db.execute(
                    select(QueryLog)
                    .where(
                        QueryLog.username == actor_username,
                        QueryLog.sqllog == "SELECT id, status FROM orders LIMIT 20;",
                    )
                    .order_by(QueryLog.id)
                    .limit(1)
                )
            ).scalar_one_or_none():
                db.add(
                    QueryLog(
                        user_id=actor_id,
                        instance_id=instance.id,
                        db_name=db_name,
                        sqllog="SELECT id, status FROM orders LIMIT 20;",
                        operation_type="execute",
                        username=actor_username,
                        instance_name=instance.instance_name,
                        db_type=instance.db_type,
                        client_ip="127.0.0.1",
                        effect_row=20,
                        cost_time_ms=86,
                        priv_check=True,
                    )
                )
                created.append("在线查询演示记录")
            else:
                skipped.append("在线查询演示记录已存在")

            if not (
                await db.execute(
                    select(ArchiveJob)
                    .where(
                        ArchiveJob.source_instance_id == instance.id,
                        ArchiveJob.source_table == "orders",
                        ArchiveJob.created_by == actor_username,
                    )
                    .order_by(ArchiveJob.id)
                    .limit(1)
                )
            ).scalar_one_or_none():
                db.add(
                    ArchiveJob(
                        status=ArchiveJobStatus.PENDING_REVIEW,
                        archive_mode="purge",
                        source_instance_id=instance.id,
                        source_db=db_name,
                        source_table="orders",
                        condition="created_at < '2025-01-01'",
                        batch_size=1000,
                        estimated_rows=12000,
                        apply_reason="商业试用演示：历史订单归档清理。",
                        risk_plan=json.dumps(
                            {"backup": "执行前导出影响范围，保留 7 天恢复窗口"},
                            ensure_ascii=False,
                        ),
                        risk_level="medium",
                        risk_summary="批量归档需确认业务低峰期和备份策略。",
                        created_by=actor_username,
                        created_by_id=actor_id,
                    )
                )
                created.append("归档作业演示记录")
            else:
                skipped.append("归档作业演示记录已存在")

            if not (
                await db.execute(
                    select(MonitorMetricSnapshot)
                    .where(
                        MonitorMetricSnapshot.instance_id == instance.id,
                        MonitorMetricSnapshot.version == "commercial-demo",
                    )
                    .order_by(MonitorMetricSnapshot.id)
                    .limit(1)
                )
            ).scalar_one_or_none():
                db.add(
                    MonitorMetricSnapshot(
                        instance_id=instance.id,
                        collected_at=_now(),
                        status="success",
                        is_up=True,
                        version="commercial-demo",
                        uptime_seconds=86400,
                        current_connections=18,
                        active_sessions=3,
                        max_connections=500,
                        connection_usage=0.036,
                        qps=128.5,
                        tps=42.0,
                        slow_queries=2,
                        error_count=0,
                        lock_waits=1,
                        total_size_bytes=32 * 1024 * 1024 * 1024,
                        extra_metrics={"source": DEMO_MARKER},
                    )
                )
                created.append("监控指标演示快照")
            else:
                skipped.append("监控指标演示快照已存在")
        else:
            skipped.append("未发现活跃实例，已跳过实例链路演示数据")

        if not (
            await db.execute(
                select(OperationLog)
                .where(
                    OperationLog.action == "commercial_trial_bootstrap_sample",
                    OperationLog.username == actor_username,
                )
                .order_by(OperationLog.id)
                .limit(1)
            )
        ).scalar_one_or_none():
            db.add(
                OperationLog(
                    user_id=actor_id,
                    username=actor_username,
                    action="commercial_trial_bootstrap_sample",
                    module="delivery",
                    detail="商业试用环境初始化样例审计记录",
                    result="success",
                )
            )
            created.append("审计演示记录")
        else:
            skipped.append("审计演示记录已存在")

        await db.commit()

        existing_runs = (
            await db.execute(
                select(DeliveryAcceptanceRun)
                .where(DeliveryAcceptanceRun.created_by == actor_username)
                .order_by(DeliveryAcceptanceRun.id.desc())
                .limit(20)
            )
        ).scalars().all()
        run = next(
            (
                item
                for item in existing_runs
                if (item.options or {}).get("source") == DEMO_MARKER
            ),
            None,
        )
        if not run:
            run = await CommercialOpsService.create_acceptance_run(
                db,
                user,
                {
                    "source": DEMO_MARKER,
                    "instance_id": instance.id if instance else None,
                    "db_name": db_name,
                },
            )
            created.append("商业试用验收报告")
        else:
            skipped.append("商业试用验收报告已存在")

        return {
            "status": "success",
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "acceptance_run": CommercialOpsService.run_to_dict(run),
            "onboarding": await CommercialOpsService.onboarding_status(db),
            "readiness": await CommercialOpsService.commercial_readiness(db),
        }

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
        project_name = report.get("project") or LICENSE_PROJECT_NAME
        lines = [
            f"# {project_name} 商业交付验收报告",
            "",
            f"- 项目：{project_name}（{report.get('project_code')}）",
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
                "version": COMMERCIAL_VERSION,
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
            f"# {LICENSE_PROJECT_NAME} 合规报表：{report['report_type']}",
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
                "read_only_metadata": "只读/元数据边界",
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
            "version": COMMERCIAL_VERSION,
            "project": LICENSE_PROJECT_NAME,
            "project_code": LICENSE_PROJECT_CODE,
            "deployment_mode": "commercial" if settings.SAGITTA_CONTROL_COMMERCIAL_BUILD else "standard",
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
