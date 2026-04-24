"""
数据脱敏规则服务 + 工单模板服务（Pack D）。
"""
from __future__ import annotations

import logging

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.models.approval_flow import ApprovalFlow
from app.models.masking import MaskingRule, WorkflowTemplate

logger = logging.getLogger(__name__)

# ── 规则类型元数据（用于前端展示）─────────────────────────────
RULE_TYPES = [
    {"value": "email",   "label": "邮箱",   "example": "ab****@domain.com", "desc": "保留前2位和@后内容"},
    {"value": "phone",   "label": "手机号", "example": "138****78",         "desc": "保留前3位和后2位"},
    {"value": "card",    "label": "银行卡", "example": "622202 **** **** 1234", "desc": "保留前6位和后4位"},
    {"value": "id_card", "label": "身份证", "example": "110***********1234", "desc": "保留前3位和后4位"},
    {"value": "name",    "label": "姓名",   "example": "张**",               "desc": "保留姓氏"},
    {"value": "address", "label": "地址",   "example": "北京市朝阳区***",    "desc": "保留前6个字符"},
    {"value": "regex",   "label": "自定义正则", "example": "",               "desc": "使用自定义正则表达式"},
]

WORKFLOW_TEMPLATE_CATEGORIES = [
    {"value": "cleanup", "label": "数据清理"},
    {"value": "repair", "label": "数据修复"},
    {"value": "index", "label": "索引变更"},
    {"value": "schema", "label": "表结构变更"},
    {"value": "inspection", "label": "巡检查询"},
    {"value": "readonly", "label": "只读分析"},
    {"value": "other", "label": "其他"},
]


class MaskingRuleService:

    @staticmethod
    def fmt(rule: MaskingRule) -> dict:
        return {
            "id": rule.id,
            "rule_name": rule.rule_name,
            "description": rule.description,
            "is_active": rule.is_active,
            "instance_id": rule.instance_id,
            "db_name": rule.db_name,
            "table_name": rule.table_name,
            "column_name": rule.column_name,
            "rule_type": rule.rule_type,
            "rule_regex": rule.rule_regex,
            "rule_regex_replace": rule.rule_regex_replace,
            "hide_group": rule.hide_group,
            "created_by": rule.created_by,
            "created_at": rule.created_at.isoformat() if rule.created_at else "",
        }

    @staticmethod
    async def list_rules(
        db: AsyncSession,
        instance_id: int | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict]]:
        conditions = []
        if instance_id is not None:
            conditions.append(MaskingRule.instance_id == instance_id)
        if is_active is not None:
            conditions.append(MaskingRule.is_active == is_active)
        if search:
            conditions.append(
                MaskingRule.rule_name.ilike(f"%{search}%") |
                MaskingRule.column_name.ilike(f"%{search}%")
            )

        count_stmt = select(func.count()).select_from(MaskingRule)
        data_stmt = select(MaskingRule)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
            data_stmt = data_stmt.where(and_(*conditions))

        total = (await db.execute(count_stmt)).scalar_one()
        data_stmt = data_stmt.order_by(MaskingRule.created_at.desc())
        data_stmt = data_stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(data_stmt)).scalars().all()
        return total, [MaskingRuleService.fmt(r) for r in rows]

    @staticmethod
    async def create_rule(db: AsyncSession, data: dict, operator: dict) -> MaskingRule:
        rule = MaskingRule(
            rule_name=data["rule_name"],
            description=data.get("description", ""),
            is_active=data.get("is_active", True),
            instance_id=data.get("instance_id"),
            db_name=data.get("db_name", "*"),
            table_name=data.get("table_name", "*"),
            column_name=data["column_name"],
            rule_type=data["rule_type"],
            rule_regex=data.get("rule_regex", ""),
            rule_regex_replace=data.get("rule_regex_replace", "***"),
            hide_group=data.get("hide_group", 0),
            created_by=operator.get("username", ""),
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def update_rule(db: AsyncSession, rule_id: int, data: dict) -> MaskingRule:
        result = await db.execute(select(MaskingRule).where(MaskingRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise NotFoundException(f"脱敏规则 ID={rule_id} 不存在")
        for field in ["rule_name", "description", "is_active", "instance_id",
                      "db_name", "table_name", "column_name", "rule_type",
                      "rule_regex", "rule_regex_replace", "hide_group"]:
            if field in data:
                setattr(rule, field, data[field])
        await db.commit()
        await db.refresh(rule)
        return rule

    @staticmethod
    async def delete_rule(db: AsyncSession, rule_id: int) -> None:
        result = await db.execute(select(MaskingRule).where(MaskingRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise NotFoundException(f"脱敏规则 ID={rule_id} 不存在")
        await db.delete(rule)
        await db.commit()

    @staticmethod
    async def get_rules_for_instance(
        db: AsyncSession, instance_id: int, db_name: str
    ) -> list[dict]:
        """
        获取适用于指定实例和数据库的活跃规则（供查询时脱敏使用）。
        匹配逻辑：instance_id 匹配 OR instance_id IS NULL（全局规则）
                   AND db_name 匹配 OR db_name='*'
        """
        stmt = select(MaskingRule).where(
            and_(
                MaskingRule.is_active,
                or_(
                    MaskingRule.instance_id == instance_id,
                    MaskingRule.instance_id.is_(None),
                ),
                or_(MaskingRule.db_name == db_name, MaskingRule.db_name == "*"),
            )
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [MaskingRuleService.fmt(r) for r in rows]

    @staticmethod
    async def preview_mask(value: str, rule_type: str,
                           rule_regex: str = "", rule_regex_replace: str = "***",
                           hide_group: int = 0) -> str:
        """实时预览脱敏效果（不写数据库）。"""
        from app.services.masking import DataMaskingService
        svc = DataMaskingService(rules=[{
            "column_name": "_preview",
            "rule_type": rule_type,
            "rule_regex": rule_regex,
            "rule_regex_replace": rule_regex_replace,
            "hide_group": hide_group,
        }])
        return svc._apply_rule(value, {
            "rule_type": rule_type,
            "rule_regex": rule_regex,
            "rule_regex_replace": rule_regex_replace,
            "hide_group": hide_group,
        })


# ═══════════════════════════════════════════════════════════
# 工单模板服务
# ═══════════════════════════════════════════════════════════

class WorkflowTemplateService:
    @staticmethod
    def _can_manage_public_template(operator: dict) -> bool:
        if operator.get("is_superuser"):
            return True
        permissions = set(operator.get("permissions") or [])
        return bool({"sql_review", "sql_execute"} & permissions)

    @staticmethod
    async def _flow_name_map(db: AsyncSession, flow_ids: list[int]) -> dict[int, str]:
        if not flow_ids:
            return {}
        rows = (
            await db.execute(
                select(ApprovalFlow.id, ApprovalFlow.name).where(ApprovalFlow.id.in_(flow_ids))
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def fmt(t: WorkflowTemplate, flow_name: str = "") -> dict:
        return {
            "id": t.id,
            "template_name": t.template_name,
            "category": t.category,
            "description": t.description,
            "scene_desc": t.scene_desc,
            "risk_hint": t.risk_hint,
            "rollback_hint": t.rollback_hint,
            "instance_id": t.instance_id,
            "db_name": t.db_name,
            "flow_id": t.flow_id,
            "flow_name": flow_name,
            "sql_content": t.sql_content,
            "syntax_type": t.syntax_type,
            "is_active": t.is_active,
            "visibility": t.visibility,
            "created_by": t.created_by,
            "created_by_id": t.created_by_id,
            "use_count": t.use_count,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "updated_at": t.updated_at.isoformat() if t.updated_at else "",
        }

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        user: dict,
        search: str | None = None,
        category: str | None = None,
        visibility: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[dict]]:
        # 可见：公开模板 + 自己创建的私有模板
        user_id = user.get("id", 0)
        visibility_cond = (
            (WorkflowTemplate.visibility == "public") |
            (WorkflowTemplate.created_by_id == user_id)
        )
        conditions = [visibility_cond]
        if search:
            conditions.append(
                WorkflowTemplate.template_name.ilike(f"%{search}%")
                | WorkflowTemplate.description.ilike(f"%{search}%")
            )
        if category:
            conditions.append(WorkflowTemplate.category == category)
        if visibility:
            conditions.append(WorkflowTemplate.visibility == visibility)
        if is_active is not None:
            conditions.append(WorkflowTemplate.is_active == is_active)

        count_stmt = select(func.count()).select_from(WorkflowTemplate).where(and_(*conditions))
        data_stmt = select(WorkflowTemplate).where(and_(*conditions))

        total = (await db.execute(count_stmt)).scalar_one()
        data_stmt = data_stmt.order_by(
            WorkflowTemplate.is_active.desc(),
            WorkflowTemplate.use_count.desc(),
            WorkflowTemplate.created_at.desc(),
        ).offset((page - 1) * page_size).limit(page_size)

        rows = (await db.execute(data_stmt)).scalars().all()
        flow_map = await WorkflowTemplateService._flow_name_map(
            db, [t.flow_id for t in rows if t.flow_id]
        )
        return total, [WorkflowTemplateService.fmt(t, flow_map.get(t.flow_id or 0, "")) for t in rows]

    @staticmethod
    async def get_template(db: AsyncSession, tmpl_id: int, user: dict) -> dict:
        user_id = user.get("id", 0)
        result = await db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.id == tmpl_id,
                (WorkflowTemplate.visibility == "public")
                | (WorkflowTemplate.created_by_id == user_id),
            )
        )
        t = result.scalar_one_or_none()
        if not t:
            raise NotFoundException(f"模板 ID={tmpl_id} 不存在")
        flow_map = await WorkflowTemplateService._flow_name_map(
            db, [t.flow_id] if t.flow_id else []
        )
        return WorkflowTemplateService.fmt(t, flow_map.get(t.flow_id or 0, ""))

    @staticmethod
    async def create_template(db: AsyncSession, data: dict, operator: dict) -> WorkflowTemplate:
        visibility = data.get("visibility", "public")
        if visibility == "public" and not WorkflowTemplateService._can_manage_public_template(operator):
            raise AppException("仅 DBA 或超级管理员可创建全局模板", code=403)
        t = WorkflowTemplate(
            template_name=data["template_name"],
            category=data.get("category", "other"),
            description=data.get("description", ""),
            scene_desc=data.get("scene_desc", ""),
            risk_hint=data.get("risk_hint", ""),
            rollback_hint=data.get("rollback_hint", ""),
            instance_id=data.get("instance_id"),
            db_name=data.get("db_name", ""),
            flow_id=data.get("flow_id"),
            sql_content=data["sql_content"],
            syntax_type=data.get("syntax_type", 0),
            is_active=data.get("is_active", True),
            visibility=visibility,
            created_by=operator.get("username", ""),
            created_by_id=operator.get("id", 0),
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return t

    @staticmethod
    async def update_template(db: AsyncSession, tmpl_id: int, data: dict, operator: dict) -> WorkflowTemplate:
        result = await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tmpl_id))
        t = result.scalar_one_or_none()
        if not t:
            raise NotFoundException(f"模板 ID={tmpl_id} 不存在")
        # 只有创建者或超管可修改
        if not operator.get("is_superuser") and t.created_by_id != operator.get("id"):
            raise AppException("无权修改此模板", code=403)
        if (
            data.get("visibility") == "public"
            and not WorkflowTemplateService._can_manage_public_template(operator)
        ):
            raise AppException("仅 DBA 或超级管理员可将模板设为全局模板", code=403)
        for field in [
            "template_name", "category", "description", "scene_desc", "risk_hint",
            "rollback_hint", "instance_id", "db_name", "flow_id",
            "sql_content", "syntax_type", "visibility", "is_active",
        ]:
            if field in data:
                setattr(t, field, data[field])
        await db.commit()
        await db.refresh(t)
        return t

    @staticmethod
    async def delete_template(db: AsyncSession, tmpl_id: int, operator: dict) -> None:
        result = await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tmpl_id))
        t = result.scalar_one_or_none()
        if not t:
            raise NotFoundException(f"模板 ID={tmpl_id} 不存在")
        if not operator.get("is_superuser") and t.created_by_id != operator.get("id"):
            raise AppException("无权删除此模板", code=403)
        await db.delete(t)
        await db.commit()

    @staticmethod
    async def use_template(db: AsyncSession, tmpl_id: int) -> WorkflowTemplate:
        """使用模板（使用次数+1）。"""
        result = await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.id == tmpl_id))
        t = result.scalar_one_or_none()
        if not t:
            raise NotFoundException(f"模板 ID={tmpl_id} 不存在")
        if not t.is_active:
            raise AppException("模板已停用，无法继续使用", code=400)
        t.use_count += 1
        await db.commit()
        await db.refresh(t)
        return t

    @staticmethod
    async def clone_template(db: AsyncSession, tmpl_id: int, operator: dict) -> WorkflowTemplate:
        data = await WorkflowTemplateService.get_template(db, tmpl_id, operator)
        cloned = WorkflowTemplate(
            template_name=f"{data['template_name']}-副本",
            category=data.get("category", "other"),
            description=data.get("description", ""),
            scene_desc=data.get("scene_desc", ""),
            risk_hint=data.get("risk_hint", ""),
            rollback_hint=data.get("rollback_hint", ""),
            instance_id=data.get("instance_id"),
            db_name=data.get("db_name", ""),
            flow_id=data.get("flow_id"),
            sql_content=data.get("sql_content", ""),
            syntax_type=data.get("syntax_type", 0),
            is_active=True,
            visibility="private",
            created_by=operator.get("username", ""),
            created_by_id=operator.get("id", 0),
            use_count=0,
        )
        db.add(cloned)
        await db.commit()
        await db.refresh(cloned)
        return cloned
