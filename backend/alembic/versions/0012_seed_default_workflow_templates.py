"""seed default workflow templates with normalized multiline SQL

Revision ID: 0012_workflow_templates_seed
Revises: 0011_workflow_template_v1
Create Date: 2026-04-18 17:25:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_workflow_templates_seed"
down_revision = "0011_workflow_template_v1"
branch_labels = None
depends_on = None


workflow_template = sa.table(
    "workflow_template",
    sa.column("template_name", sa.String()),
    sa.column("category", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("scene_desc", sa.Text()),
    sa.column("risk_hint", sa.Text()),
    sa.column("rollback_hint", sa.Text()),
    sa.column("instance_id", sa.Integer()),
    sa.column("db_name", sa.String()),
    sa.column("flow_id", sa.Integer()),
    sa.column("sql_content", sa.Text()),
    sa.column("syntax_type", sa.Integer()),
    sa.column("is_active", sa.Boolean()),
    sa.column("visibility", sa.String()),
    sa.column("created_by", sa.String()),
    sa.column("created_by_id", sa.Integer()),
    sa.column("use_count", sa.Integer()),
    sa.column("tenant_id", sa.Integer()),
)


DEFAULT_TEMPLATES = [
    {
        "template_name": "数据清理-按条件删除历史数据",
        "category": "cleanup",
        "description": "用于小范围、一次性的临时 SQL 删除；大批量历史清理请优先使用数据归档。",
        "scene_desc": "适用于少量异常数据或一次性人工 SQL 清理。定期清理、分批限速、跨库迁移等场景请使用数据归档。",
        "risk_hint": "删除类操作不可逆，必须先补全校验 SQL 并确认影响行数；大表按条件历史清理建议改走数据归档审批作业。",
        "rollback_hint": "执行前先备份受影响数据；如已删除需通过备份表或 binlog/归档数据回补。",
        "sql_content": """-- 请先将 SELECT 校验语句补充完整
SELECT COUNT(*) AS affected_rows
FROM your_table
WHERE your_condition;

-- 确认无误后再执行清理
DELETE FROM your_table
WHERE your_condition;""",
        "syntax_type": 2,
    },
    {
        "template_name": "数据修复-按主键修正业务字段",
        "category": "repair",
        "description": "用于按主键或唯一键修正少量业务字段数据。",
        "scene_desc": "适用于因业务异常、脚本缺陷导致的单批次错误数据修复场景。",
        "risk_hint": "必须明确修复范围和目标值，避免大面积误更新；建议先查询确认后执行。",
        "rollback_hint": "执行前导出修复前数据，保留主键与原值，必要时使用反向 UPDATE 回滚。",
        "sql_content": """-- 修复前校验
SELECT *
FROM your_table
WHERE id IN (...);

-- 执行修复
UPDATE your_table
SET target_column = new_value
WHERE id IN (...);""",
        "syntax_type": 2,
    },
    {
        "template_name": "索引变更-新增普通索引",
        "category": "index",
        "description": "用于为高频查询条件新增普通索引。",
        "scene_desc": "适用于慢查询优化、固定查询条件优化等场景，需要附带 EXPLAIN 或慢 SQL 依据。",
        "risk_hint": "新增索引会增加写入成本和存储消耗，执行前需评估重复索引和影响范围。",
        "rollback_hint": "记录索引名称，必要时使用 DROP INDEX 或 ALTER TABLE DROP INDEX 回滚。",
        "sql_content": """-- 建议先提供 EXPLAIN 结果和索引命名说明
ALTER TABLE your_table
ADD INDEX idx_your_table_col1_col2 (col1, col2);

-- 回滚示例
-- ALTER TABLE your_table DROP INDEX idx_your_table_col1_col2;""",
        "syntax_type": 1,
    },
    {
        "template_name": "表结构变更-新增字段",
        "category": "schema",
        "description": "用于为业务表新增字段并补充默认值和注释。",
        "scene_desc": "适用于业务扩展需要增加新字段的场景，需说明兼容性与应用发布计划。",
        "risk_hint": "DDL 可能影响锁等待与发布节奏，需评估是否在线变更及应用兼容情况。",
        "rollback_hint": "确认应用未依赖该字段后，可执行 DROP COLUMN 回滚。",
        "sql_content": """-- 新增字段示例
ALTER TABLE your_table
ADD COLUMN new_column VARCHAR(64) NOT NULL DEFAULT 'default_value' COMMENT '字段说明';

-- 回滚示例
-- ALTER TABLE your_table DROP COLUMN new_column;""",
        "syntax_type": 1,
    },
    {
        "template_name": "巡检查询-表数据与异常巡检",
        "category": "inspection",
        "description": "用于检查表数据量、异常状态和近周期波动情况。",
        "scene_desc": "适用于日常巡检、上线后观测、异常事件排查等场景。",
        "risk_hint": "巡检 SQL 应尽量走索引并控制返回行数，避免对业务库造成明显压力。",
        "rollback_hint": "查询类操作无需回滚，如需进一步处理请单独提交修复或清理工单。",
        "sql_content": """-- 示例：近 7 天异常状态巡检
SELECT status, COUNT(*) AS cnt
FROM your_table
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY status
ORDER BY cnt DESC
LIMIT 100;""",
        "syntax_type": 0,
    },
    {
        "template_name": "只读分析-聚合统计分析",
        "category": "readonly",
        "description": "用于只读分析、运营核对和聚合统计查询。",
        "scene_desc": "适用于报表核对、临时分析、问题定位等只读查询场景。",
        "risk_hint": "需控制时间范围、过滤条件和返回行数，避免大表全扫。",
        "rollback_hint": "查询类操作无需回滚。",
        "sql_content": """-- 示例：按维度聚合分析
SELECT biz_date, category, COUNT(*) AS total_cnt, SUM(amount) AS total_amount
FROM your_table
WHERE biz_date BETWEEN '2026-04-01' AND '2026-04-30'
GROUP BY biz_date, category
ORDER BY biz_date DESC, total_cnt DESC
LIMIT 200;""",
        "syntax_type": 0,
    },
    {
        "template_name": "其他-通用 SQL 工单",
        "category": "other",
        "description": "用于临时性、一次性或需要自由填写的通用 SQL 工单场景。",
        "scene_desc": "适用于无法归类到标准模板、但仍希望遵循统一提单规范的场景。",
        "risk_hint": "请补充执行背景、影响范围、风险评估和验证方式。",
        "rollback_hint": "请根据实际 SQL 类型填写回滚 SQL 或回滚步骤。",
        "sql_content": """-- 请根据实际场景补充 SQL
-- 建议先写校验 SQL，再写执行 SQL
SELECT 1;""",
        "syntax_type": 0,
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    admin_flow_id = conn.execute(
        sa.text(
            """
            SELECT id
            FROM approval_flow
            WHERE is_active = true
            ORDER BY id
            LIMIT 1
            """
        )
    ).scalar()

    for item in DEFAULT_TEMPLATES:
        existing = conn.execute(
            sa.text(
                """
                SELECT id
                FROM workflow_template
                WHERE template_name = :template_name
                LIMIT 1
                """
            ),
            {"template_name": item["template_name"]},
        ).scalar()

        payload = {
            **item,
            "instance_id": None,
            "db_name": "",
            "flow_id": admin_flow_id,
            "is_active": True,
            "visibility": "public",
            "created_by": "admin",
            "created_by_id": 1,
            "use_count": 0,
            "tenant_id": 1,
        }

        if existing:
            conn.execute(
                sa.text(
                    """
                    UPDATE workflow_template
                    SET category = :category,
                        description = :description,
                        scene_desc = :scene_desc,
                        risk_hint = :risk_hint,
                        rollback_hint = :rollback_hint,
                        instance_id = :instance_id,
                        db_name = :db_name,
                        flow_id = :flow_id,
                        sql_content = :sql_content,
                        syntax_type = :syntax_type,
                        is_active = :is_active,
                        visibility = :visibility,
                        created_by = :created_by,
                        created_by_id = :created_by_id,
                        tenant_id = :tenant_id
                    WHERE id = :id
                    """
                ),
                {**payload, "id": existing},
            )
        else:
            op.bulk_insert(workflow_template, [payload])


def downgrade() -> None:
    conn = op.get_bind()
    names = [item["template_name"] for item in DEFAULT_TEMPLATES]
    conn.execute(
        sa.text("DELETE FROM workflow_template WHERE template_name IN :names").bindparams(
            sa.bindparam("names", expanding=True)
        ),
        {"names": names},
    )
