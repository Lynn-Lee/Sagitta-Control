"""
数据脱敏规则模型（Pack D）。
支持 7 种内置规则类型 + 自定义正则，可按实例/数据库/表/列精确匹配。
"""
from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MaskingRule(BaseModel):
    """
    数据脱敏规则表。
    匹配优先级：column_name > table_name > db_name（越精确越优先）。
    """
    __tablename__ = "masking_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── 规则名称与说明 ────────────────────────────────────────
    rule_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="规则名称")
    description: Mapped[str] = mapped_column(String(200), default="", comment="规则说明")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    # ── 匹配范围（精确到列）──────────────────────────────────
    instance_id: Mapped[int | None] = mapped_column(Integer, comment="适用实例ID，NULL=所有实例")
    db_name: Mapped[str] = mapped_column(String(64), default="*", comment="数据库名，*=所有")
    table_name: Mapped[str] = mapped_column(String(64), default="*", comment="表名，*=所有")
    column_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="列名（支持*通配）")

    # ── 脱敏规则类型 ─────────────────────────────────────────
    # email / phone / card / id_card / name / address / regex
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="规则类型")

    # 自定义正则规则（rule_type=regex 时生效）
    rule_regex: Mapped[str] = mapped_column(String(500), default="", comment="自定义正则表达式")
    rule_regex_replace: Mapped[str] = mapped_column(String(100), default="***", comment="替换字符串")
    # 三段式脱敏：隐藏第几组，0=不使用分组模式
    hide_group: Mapped[int] = mapped_column(Integer, default=0, comment="隐藏正则分组序号")

    # ── 元数据 ────────────────────────────────────────────────
    created_by: Mapped[str] = mapped_column(String(30), default="", comment="创建人")

    __table_args__ = (
        Index("ix_masking_instance", "instance_id"),
        Index("ix_masking_active", "is_active"),
        Index("ix_masking_tenant", "tenant_id"),
    )


class WorkflowTemplate(BaseModel):
    """
    SQL 工单模板表（Pack D）。
    用于保存常用 SQL 模板，提交工单时快速套用，减少重复劳动。
    """
    __tablename__ = "workflow_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="模板名称")
    category: Mapped[str] = mapped_column(String(30), default="other", comment="模板分类")
    description: Mapped[str] = mapped_column(String(200), default="", comment="模板说明")
    scene_desc: Mapped[str] = mapped_column(String(300), default="", comment="适用场景")
    risk_hint: Mapped[str] = mapped_column(String(300), default="", comment="风险提示")
    rollback_hint: Mapped[str] = mapped_column(String(300), default="", comment="回滚建议")

    # 默认关联的实例和数据库（提交工单时自动填充）
    instance_id: Mapped[int | None] = mapped_column(Integer, comment="默认实例ID")
    db_name: Mapped[str] = mapped_column(String(64), default="", comment="默认数据库名")
    flow_id: Mapped[int | None] = mapped_column(Integer, comment="默认审批流ID")

    sql_content: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 模板内容")
    syntax_type: Mapped[int] = mapped_column(Integer, default=0, comment="SQL类型 0未知 1DDL 2DML")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    # 可见范围：public=全局模板 private=个人模板
    visibility: Mapped[str] = mapped_column(String(10), default="public", comment="可见范围")
    created_by: Mapped[str] = mapped_column(String(30), default="", comment="创建人")
    created_by_id: Mapped[int] = mapped_column(Integer, default=0, comment="创建人ID")

    # 使用次数统计
    use_count: Mapped[int] = mapped_column(Integer, default=0, comment="使用次数")

    __table_args__ = (
        Index("ix_tmpl_created_by", "created_by_id"),
        Index("ix_tmpl_visibility", "visibility"),
        Index("ix_tmpl_category", "category"),
        Index("ix_tmpl_active", "is_active"),
        Index("ix_tmpl_tenant", "tenant_id"),
    )
