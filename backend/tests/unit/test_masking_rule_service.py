"""`MaskingRuleService` 与 `WorkflowTemplateService` 单测（此前约 21% 覆盖）。

以 AsyncMock 隔离 DB，覆盖脱敏规则 CRUD、实例规则匹配、预览，以及工单模板
的可见性过滤、权限校验（创建者/DBA/超管）、使用计数与克隆。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.services.masking_rule import MaskingRuleService, WorkflowTemplateService


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _one(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _count(n: int) -> MagicMock:
    r = MagicMock()
    r.scalar_one.return_value = n
    return r


def _scalars(rows) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _rows(rows) -> MagicMock:
    r = MagicMock()
    r.all.return_value = rows
    return r


def _rule() -> SimpleNamespace:
    return SimpleNamespace(
        id=1, rule_name="邮箱脱敏", description="d", is_active=True, instance_id=1,
        db_name="*", table_name="*", column_name="email", rule_type="email",
        rule_regex="", rule_regex_replace="***", hide_group=0, created_by="admin",
        created_at=datetime(2026, 1, 1),
    )


def _tmpl(**over) -> SimpleNamespace:
    base = dict(
        id=1, template_name="巡检", category="inspection", description="d", scene_desc="s",
        risk_hint="r", rollback_hint="rb", instance_id=1, db_name="shop", flow_id=None,
        sql_content="SELECT 1", syntax_type=0, is_active=True, visibility="public",
        created_by="admin", created_by_id=1, use_count=0,
        created_at=datetime(2026, 1, 1), updated_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# ══════════ MaskingRuleService ══════════

@pytest.mark.asyncio
async def test_list_rules_with_filters_and_pagination():
    db = _make_db()
    db.execute.side_effect = [_count(1), _scalars([_rule()])]
    total, items = await MaskingRuleService.list_rules(db, instance_id=1, is_active=True, search="邮箱")
    assert total == 1
    assert items[0]["rule_name"] == "邮箱脱敏"
    assert items[0]["created_at"].startswith("2026")


@pytest.mark.asyncio
async def test_create_rule_defaults_applied():
    db = _make_db()
    rule = await MaskingRuleService.create_rule(
        db, {"rule_name": "r", "column_name": "c", "rule_type": "phone"}, {"username": "u"}
    )
    assert rule.db_name == "*"
    assert rule.rule_regex_replace == "***"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_sets_fields():
    rule = _rule()
    db = _make_db()
    db.execute.return_value = _one(rule)
    out = await MaskingRuleService.update_rule(db, 1, {"rule_name": "新名", "is_active": False})
    assert out.rule_name == "新名"
    assert out.is_active is False


@pytest.mark.asyncio
async def test_update_rule_missing_raises():
    db = _make_db()
    db.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await MaskingRuleService.update_rule(db, 404, {})


@pytest.mark.asyncio
async def test_delete_rule_found_and_missing():
    rule = _rule()
    db = _make_db()
    db.execute.return_value = _one(rule)
    await MaskingRuleService.delete_rule(db, 1)
    db.delete.assert_awaited_once()

    db2 = _make_db()
    db2.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await MaskingRuleService.delete_rule(db2, 404)


@pytest.mark.asyncio
async def test_get_rules_for_instance():
    db = _make_db()
    db.execute.return_value = _scalars([_rule()])
    out = await MaskingRuleService.get_rules_for_instance(db, instance_id=1, db_name="shop")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_preview_mask_masks_value():
    out = await MaskingRuleService.preview_mask("13800138000", "phone")
    assert "*" in out


# ══════════ WorkflowTemplateService ══════════

def test_can_manage_public_template():
    assert WorkflowTemplateService._can_manage_public_template({"is_superuser": True}) is True
    assert WorkflowTemplateService._can_manage_public_template({"permissions": ["sql_review"]}) is True
    assert WorkflowTemplateService._can_manage_public_template({"permissions": ["other"]}) is False


@pytest.mark.asyncio
async def test_flow_name_map_empty_short_circuits():
    db = _make_db()
    assert await WorkflowTemplateService._flow_name_map(db, []) == {}
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_flow_name_map_builds_dict():
    db = _make_db()
    db.execute.return_value = _rows([(2, "审批A")])
    assert await WorkflowTemplateService._flow_name_map(db, [2]) == {2: "审批A"}


@pytest.mark.asyncio
async def test_list_templates_joins_flow_name():
    db = _make_db()
    db.execute.side_effect = [_count(1), _scalars([_tmpl(flow_id=2)]), _rows([(2, "审批A")])]
    total, items = await WorkflowTemplateService.list_templates(db, {"id": 1}, search="巡检", category="inspection")
    assert total == 1
    assert items[0]["flow_name"] == "审批A"


@pytest.mark.asyncio
async def test_get_template_found_and_missing():
    db = _make_db()
    db.execute.return_value = _one(_tmpl())
    out = await WorkflowTemplateService.get_template(db, 1, {"id": 1})
    assert out["template_name"] == "巡检"

    db2 = _make_db()
    db2.execute.return_value = _one(None)
    with pytest.raises(NotFoundException):
        await WorkflowTemplateService.get_template(db2, 404, {"id": 1})


@pytest.mark.asyncio
async def test_create_template_public_requires_dba():
    db = _make_db()
    with pytest.raises(AppException):
        await WorkflowTemplateService.create_template(
            db, {"template_name": "t", "sql_content": "s", "visibility": "public"},
            {"id": 1, "permissions": []},
        )


@pytest.mark.asyncio
async def test_create_template_success_for_superuser():
    db = _make_db()
    t = await WorkflowTemplateService.create_template(
        db, {"template_name": "t", "sql_content": "s", "visibility": "public"},
        {"is_superuser": True, "username": "admin", "id": 1},
    )
    assert t.template_name == "t"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_template_permission_denied():
    db = _make_db()
    db.execute.return_value = _one(_tmpl(created_by_id=1))
    with pytest.raises(AppException):
        await WorkflowTemplateService.update_template(db, 1, {}, {"id": 2, "is_superuser": False})


@pytest.mark.asyncio
async def test_update_template_public_visibility_denied():
    db = _make_db()
    db.execute.return_value = _one(_tmpl(created_by_id=1))
    with pytest.raises(AppException):
        await WorkflowTemplateService.update_template(
            db, 1, {"visibility": "public"}, {"id": 1, "is_superuser": False, "permissions": []}
        )


@pytest.mark.asyncio
async def test_update_template_success():
    t = _tmpl(created_by_id=1)
    db = _make_db()
    db.execute.return_value = _one(t)
    out = await WorkflowTemplateService.update_template(
        db, 1, {"template_name": "改", "category": "other"},
        {"id": 1, "is_superuser": True},
    )
    assert out.template_name == "改"


@pytest.mark.asyncio
async def test_delete_template_missing_perm_and_success():
    db = _make_db()
    db.execute.return_value = _one(_tmpl(created_by_id=1))
    with pytest.raises(AppException):
        await WorkflowTemplateService.delete_template(db, 1, {"id": 2, "is_superuser": False})

    db2 = _make_db()
    db2.execute.return_value = _one(_tmpl(created_by_id=1))
    await WorkflowTemplateService.delete_template(db2, 1, {"id": 1, "is_superuser": False})
    db2.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_template_increments_and_guards():
    t = _tmpl(use_count=5)
    db = _make_db()
    db.execute.return_value = _one(t)
    out = await WorkflowTemplateService.use_template(db, 1)
    assert out.use_count == 6

    db2 = _make_db()
    db2.execute.return_value = _one(_tmpl(is_active=False))
    with pytest.raises(AppException):
        await WorkflowTemplateService.use_template(db2, 1)


@pytest.mark.asyncio
async def test_clone_template_creates_private_copy():
    db = _make_db()
    db.execute.return_value = _one(_tmpl())  # get_template（flow_id=None，不查 flow_map）
    cloned = await WorkflowTemplateService.clone_template(db, 1, {"username": "bob", "id": 2})
    assert cloned.template_name == "巡检-副本"
    assert cloned.visibility == "private"
    assert cloned.use_count == 0
