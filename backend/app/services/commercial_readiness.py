"""实施向导和 readiness 静态规则。"""

from __future__ import annotations

from typing import Any

from app.services.commercial_ops_metadata import ONBOARDING_STEPS


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
        "fix_hint": "初始化试用环境会幂等创建用户试用资源组、团队和标准审批流。",
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


def build_onboarding_steps(completed: set[str], system_hints: dict[str, Any]) -> list[dict[str, Any]]:
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
