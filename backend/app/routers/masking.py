"""
数据脱敏规则 + 工单模板路由（Pack D）。
"""
import logging

from fastapi import APIRouter, Depends
from fastapi import Query as QParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user, require_perm
from app.services.masking_rule import (
    RULE_TYPES,
    WORKFLOW_TEMPLATE_CATEGORIES,
    MaskingRuleService,
    WorkflowTemplateService,
)

logger = logging.getLogger(__name__)
router = APIRouter()
template_router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 脱敏规则
# ═══════════════════════════════════════════════════════════

@router.get("/rule-types/", summary="支持的脱敏规则类型")
async def get_rule_types(_user=Depends(current_user)):
    return {"items": RULE_TYPES}


@router.get("/", summary="脱敏规则列表")
async def list_masking_rules(
    instance_id: int | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user=Depends(require_perm("system_config_manage")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await MaskingRuleService.list_rules(
        db, instance_id=instance_id, is_active=is_active,
        search=search, page=page, page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/", summary="创建脱敏规则")
async def create_masking_rule(
    data: dict,
    user=Depends(require_perm("system_config_manage")),
    db: AsyncSession = Depends(get_db),
):
    rule = await MaskingRuleService.create_rule(db, data, user)
    return {"status": 0, "msg": "脱敏规则创建成功", "data": {"id": rule.id}}


@router.put("/{rule_id}/", summary="更新脱敏规则")
async def update_masking_rule(
    rule_id: int, data: dict,
    user=Depends(require_perm("system_config_manage")),
    db: AsyncSession = Depends(get_db),
):
    rule = await MaskingRuleService.update_rule(db, rule_id, data)
    return {"status": 0, "msg": "已更新", "data": {"id": rule.id}}


@router.delete("/{rule_id}/", summary="删除脱敏规则")
async def delete_masking_rule(
    rule_id: int,
    user=Depends(require_perm("system_config_manage")),
    db: AsyncSession = Depends(get_db),
):
    await MaskingRuleService.delete_rule(db, rule_id)
    return {"status": 0, "msg": "已删除"}


@router.post("/preview/", summary="实时预览脱敏效果")
async def preview_masking(
    data: dict,
    _user=Depends(current_user),
):
    """
    实时预览某条数据经过脱敏后的效果，不需要保存规则。
    data: {value, rule_type, rule_regex?, rule_regex_replace?, hide_group?}
    """
    result = await MaskingRuleService.preview_mask(
        value=data.get("value", ""),
        rule_type=data.get("rule_type", "phone"),
        rule_regex=data.get("rule_regex", ""),
        rule_regex_replace=data.get("rule_regex_replace", "***"),
        hide_group=data.get("hide_group", 0),
    )
    return {"original": data.get("value", ""), "masked": result}


# ═══════════════════════════════════════════════════════════
# 工单模板
# ═══════════════════════════════════════════════════════════

@template_router.get("/", summary="工单模板列表")
async def list_templates(
    search: str | None = None,
    category: str | None = None,
    visibility: str | None = None,
    is_active: bool | None = None,
    page: int = QParam(1, ge=1),
    page_size: int = QParam(20, ge=1, le=100),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    total, items = await WorkflowTemplateService.list_templates(
        db,
        user=user,
        search=search,
        category=category,
        visibility=visibility,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@template_router.get("/categories/", summary="工单模板分类")
async def list_template_categories(_user=Depends(current_user)):
    return {"items": WORKFLOW_TEMPLATE_CATEGORIES}


@template_router.get("/{tmpl_id}/", summary="工单模板详情")
async def get_template(
    tmpl_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await WorkflowTemplateService.get_template(db, tmpl_id, user)
    return {"data": data}


@template_router.post("/", summary="创建工单模板")
async def create_template(
    data: dict,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await WorkflowTemplateService.create_template(db, data, user)
    return {"status": 0, "msg": "模板创建成功", "data": {"id": t.id}}


@template_router.put("/{tmpl_id}/", summary="更新工单模板")
async def update_template(
    tmpl_id: int, data: dict,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await WorkflowTemplateService.update_template(db, tmpl_id, data, user)
    return {"status": 0, "msg": "已更新", "data": {"id": t.id}}


@template_router.delete("/{tmpl_id}/", summary="删除工单模板")
async def delete_template(
    tmpl_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await WorkflowTemplateService.delete_template(db, tmpl_id, user)
    return {"status": 0, "msg": "已删除"}


@template_router.post("/{tmpl_id}/use/", summary="使用模板（计数+1）")
async def use_template(
    tmpl_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await WorkflowTemplateService.use_template(db, tmpl_id)
    return {"status": 0, "data": WorkflowTemplateService.fmt(t)}


@template_router.post("/{tmpl_id}/clone/", summary="复制工单模板")
async def clone_template(
    tmpl_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await WorkflowTemplateService.clone_template(db, tmpl_id, user)
    return {"status": 0, "msg": "模板复制成功", "data": {"id": t.id}}
