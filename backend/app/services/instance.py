"""
实例管理业务逻辑服务。
密码字段使用 encrypt_field / decrypt_field 加密存储（修复 1.x 明文存储问题）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import decrypt_field, encrypt_field
from app.engines.registry import get_engine
from app.models.instance import Instance, InstanceTag, SshTunnel
from app.models.user import ResourceGroup
from app.schemas.instance import (
    InstanceCreate,
    InstanceUpdate,
    TunnelCreate,
)

logger = logging.getLogger(__name__)


class InstanceService:
    @staticmethod
    def _normalize_default_expression(default_value: Any) -> str:
        if default_value in (None, ""):
            return ""
        normalized = " ".join(str(default_value).split())
        return normalized.strip()

    @staticmethod
    def _escape_sql_literal(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _build_comment_statements(
        instance: Instance,
        table_name: str,
        columns: list[dict[str, Any]],
        *,
        schema_name: str | None = None,
    ) -> list[str]:
        if instance.db_type not in {"pgsql", "oracle"}:
            return []

        if schema_name:
            table_ref = (
                f"{InstanceService._quote_identifier(instance, schema_name)}."
                f"{InstanceService._quote_identifier(instance, table_name)}"
            )
        else:
            table_ref = InstanceService._quote_identifier(instance, table_name)

        comment_lines: list[str] = []
        for column in columns:
            comment = str(column.get("column_comment") or "").strip()
            column_name = str(column.get("column_name") or "").strip()
            if not comment or not column_name:
                continue
            comment_lines.append(
                f"COMMENT ON COLUMN {table_ref}.{InstanceService._quote_identifier(instance, column_name)} "
                f"IS '{InstanceService._escape_sql_literal(comment)}';"
            )
        return comment_lines

    @staticmethod
    def _is_system_generated_constraint(constraint_name: str) -> bool:
        normalized = constraint_name.strip().upper()
        return normalized.startswith("SYS_C") or normalized.startswith("BIN$")

    @staticmethod
    def _is_simple_not_null_check(constraint: dict[str, Any]) -> bool:
        if str(constraint.get("constraint_type") or "").upper() != "CHECK":
            return False
        column_names = InstanceService._split_column_names(constraint.get("column_names"))
        if len(column_names) != 1:
            return False
        column_name = column_names[0].replace('"', "").strip().upper()
        check_clause = str(constraint.get("check_clause") or "").strip().upper()
        if not check_clause and InstanceService._is_system_generated_constraint(
            str(constraint.get("constraint_name") or "")
        ):
            return True
        compact_clause = " ".join(check_clause.replace('"', "").replace("(", " ").replace(")", " ").split())
        return compact_clause in {f"CHECK {column_name} IS NOT NULL", f"{column_name} IS NOT NULL"}

    @staticmethod
    def _should_hide_column_not_null_check(constraint: dict[str, Any]) -> bool:
        return (
            InstanceService._is_system_generated_constraint(
                str(constraint.get("constraint_name") or "")
            )
            and InstanceService._is_simple_not_null_check(constraint)
        )

    @staticmethod
    def _quote_identifier(instance: Instance, identifier: str) -> str:
        if instance.db_type in {"mysql", "tidb", "doris"}:
            return f"`{identifier}`"
        return f'"{identifier}"'

    @staticmethod
    def _split_column_names(value: str | None) -> list[str]:
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @staticmethod
    def _build_constraint_clause(
        instance: Instance,
        constraint: dict[str, Any],
    ) -> str:
        constraint_type = str(constraint.get("constraint_type") or "").upper()
        constraint_name = str(constraint.get("constraint_name") or "").strip()
        column_names = InstanceService._split_column_names(constraint.get("column_names"))
        referenced_table = str(constraint.get("referenced_table_name") or "").strip()
        referenced_columns = InstanceService._split_column_names(
            constraint.get("referenced_column_names")
        )
        check_clause = str(constraint.get("check_clause") or "").strip()

        quoted_columns = ", ".join(
            InstanceService._quote_identifier(instance, column_name)
            for column_name in column_names
        )
        named_prefix = (
            f"CONSTRAINT {InstanceService._quote_identifier(instance, constraint_name)} "
            if constraint_name and constraint_name != "PRIMARY"
            else ""
        )

        if constraint_type == "PRIMARY KEY" and quoted_columns:
            return f"PRIMARY KEY ({quoted_columns})"
        if constraint_type == "UNIQUE" and quoted_columns:
            return f"{named_prefix}UNIQUE ({quoted_columns})"
        if constraint_type == "FOREIGN KEY" and quoted_columns and referenced_table:
            quoted_ref_columns = ", ".join(
                InstanceService._quote_identifier(instance, column_name)
                for column_name in referenced_columns
            )
            ref_target = InstanceService._quote_identifier(instance, referenced_table)
            reference_clause = (
                f" REFERENCES {ref_target} ({quoted_ref_columns})"
                if quoted_ref_columns
                else f" REFERENCES {ref_target}"
            )
            return f"{named_prefix}FOREIGN KEY ({quoted_columns}){reference_clause}"
        if constraint_type == "CHECK" and check_clause:
            if InstanceService._should_hide_column_not_null_check(constraint):
                return ""
            normalized_check = check_clause
            if normalized_check.upper().startswith("CHECK"):
                normalized_check = normalized_check[5:].strip()
            if InstanceService._is_system_generated_constraint(constraint_name):
                named_prefix = ""
            return f"{named_prefix}CHECK {normalized_check}"
        return ""

    @staticmethod
    def _build_generic_table_ddl(
        instance: Instance,
        tb_name: str,
        columns: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        indexes: list[dict[str, Any]] | None = None,
    ) -> str:
        table_name = InstanceService._quote_identifier(instance, tb_name)
        lines: list[str] = []

        for column in columns:
            column_name = InstanceService._quote_identifier(
                instance, str(column.get("column_name") or "")
            )
            column_type = str(column.get("column_type") or "text").strip()
            nullable = str(column.get("is_nullable") or "YES").upper()
            default_value = InstanceService._normalize_default_expression(column.get("column_default"))
            column_parts = [column_name, column_type]
            if nullable in {"NO", "N", "FALSE"} or column.get("is_nullable") is False:
                column_parts.append("NOT NULL")
            if default_value:
                column_parts.append(f"DEFAULT {default_value}")
            lines.append(f"  {' '.join(column_parts)}")

        for constraint in constraints:
            clause = InstanceService._build_constraint_clause(instance, constraint)
            if clause:
                lines.append(f"  {clause}")

        body = ",\n".join(lines) if lines else "  -- no column metadata available"
        ddl = f"CREATE TABLE {table_name} (\n{body}\n);"

        comment_lines = InstanceService._build_comment_statements(instance, tb_name, columns)
        if comment_lines:
            ddl = f"{ddl}\n\n" + "\n".join(comment_lines)

        index_lines = InstanceService._build_index_statements(
            instance,
            tb_name,
            indexes or [],
            constraints,
        )
        if index_lines:
            ddl = f"{ddl}\n\n" + "\n".join(index_lines)

        return ddl

    @staticmethod
    def _build_index_statements(
        instance: Instance,
        tb_name: str,
        indexes: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
    ) -> list[str]:
        if instance.db_type != "pgsql":
            return []

        constraint_index_names = {
            str(item.get("constraint_name") or "").strip().lower()
            for item in constraints
            if str(item.get("constraint_type") or "").upper() in {"PRIMARY KEY", "UNIQUE"}
        }
        table_name = InstanceService._quote_identifier(instance, tb_name)
        statements: list[str] = []

        for index in indexes:
            index_name = str(index.get("index_name") or "").strip()
            if not index_name:
                continue
            index_type = str(index.get("index_type") or "").upper()
            if (
                index_name.lower() in constraint_index_names
                or "PRIMARY KEY" in index_type
                or index_name.lower().endswith("_pkey")
            ):
                continue

            definition = str(index.get("index_definition") or "").strip()
            if definition:
                statements.append(definition.rstrip(";") + ";")
                continue

            column_names = InstanceService._split_column_names(index.get("column_names"))
            if not column_names:
                continue
            quoted_columns = ", ".join(
                InstanceService._quote_identifier(instance, column_name)
                for column_name in column_names
            )
            keyword = "CREATE UNIQUE INDEX" if "UNIQUE" in index_type else "CREATE INDEX"
            statements.append(
                f"{keyword} {InstanceService._quote_identifier(instance, index_name)} "
                f"ON {table_name} ({quoted_columns});"
            )

        return statements

    @staticmethod
    def _simplify_oracle_ddl(raw_ddl: str) -> str:
        simplified = raw_ddl.replace("\r\n", "\n").replace("\r", "\n").strip()
        simplified = re.sub(
            r'CREATE\s+TABLE\s+"[^"]+"\."([^"]+)"',
            r'CREATE TABLE "\1"',
            simplified,
            count=1,
            flags=re.IGNORECASE,
        )
        simplified = re.sub(
            r'(GENERATED\s+(?:ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY)(?:\s*\([^)]*\)|(?:\s+(?:MINVALUE|MAXVALUE|NOMINVALUE|NOMAXVALUE|START\s+WITH|INCREMENT\s+BY|CACHE|NOCACHE|ORDER|NOORDER|CYCLE|NOCYCLE|KEEP|NOKEEP|SCALE|NOSCALE|\d+))+)',
            r'\1',
            simplified,
            flags=re.IGNORECASE,
        )
        simplified = re.sub(
            r'\n\s*STORAGE\s*\([^)]*\)',
            '',
            simplified,
            flags=re.IGNORECASE | re.DOTALL,
        )
        simplified = re.sub(r'\n\s*USING INDEX\b[^\n]*', '', simplified, flags=re.IGNORECASE)
        simplified = re.sub(
            r'\n\s*(?:SEGMENT\s+CREATION|PCTFREE|PCTUSED|INITRANS|MAXTRANS|NOCOMPRESS|COMPRESS|LOGGING|NOLOGGING|TABLESPACE|BUFFER_POOL|FLASH_CACHE|CELL_FLASH_CACHE)\b[^\n;]*(?:;)?',
            '',
            simplified,
            flags=re.IGNORECASE,
        )
        simplified = re.sub(r'\n\s*ENABLE\s*(?=\n|\))', '', simplified, flags=re.IGNORECASE)
        simplified = re.sub(r'\bENABLE\b', '', simplified, flags=re.IGNORECASE)
        simplified = re.sub(r'[ \t]+', ' ', simplified)
        simplified = re.sub(r' +\n', '\n', simplified)
        simplified = re.sub(r'\(\s*\n', '(\n', simplified)
        simplified = re.sub(r'\n{3,}', '\n\n', simplified)
        simplified = re.sub(r'\n\s+\)', '\n)', simplified)
        if "COMMENT ON" in simplified:
            table_ddl, comments = simplified.split("COMMENT ON", 1)
            table_ddl = table_ddl.strip()
            if table_ddl.upper().startswith("CREATE TABLE") and not table_ddl.endswith(";"):
                table_ddl += ";"
            simplified = f"{table_ddl}\n\nCOMMENT ON {comments.strip()}"
        elif simplified.upper().startswith("CREATE TABLE") and not simplified.endswith(";"):
            simplified += ";"
        return simplified.strip()

    @staticmethod
    async def _collect_table_metadata(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        tb_name: str,
    ) -> tuple[Instance, str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        inst = await InstanceService._load_instance(db, instance_id)
        resolved_table_name, extra_kwargs = InstanceService._resolve_table_lookup(
            inst, db_name, tb_name
        )
        columns = await InstanceService.get_columns(db, instance_id, db_name, tb_name)
        constraints = await InstanceService.get_constraints(db, instance_id, db_name, tb_name)
        return inst, resolved_table_name, extra_kwargs, columns, constraints

    @staticmethod
    def _resolve_table_lookup(instance: Instance, db_name: str, tb_name: str) -> tuple[str, dict[str, Any]]:
        normalized_table = tb_name.strip()
        if instance.db_type == "pgsql" and "." in normalized_table:
            schema, table_name = normalized_table.split(".", 1)
            if schema and table_name:
                return table_name, {"schema": schema}
        return normalized_table, {}

    @staticmethod
    def _normalize_column_row(
        row: dict[str, Any] | tuple[Any, ...] | list[Any],
        cols: list[str],
    ) -> dict[str, Any]:
        raw = row if isinstance(row, dict) else dict(zip(cols, row, strict=False))

        lowered = {str(key).lower(): value for key, value in raw.items()}
        normalized = {
            "column_name": lowered.get("column_name") or lowered.get("name") or "",
            "column_type": (
                lowered.get("column_type")
                or lowered.get("data_type")
                or lowered.get("type")
                or ""
            ),
            "is_nullable": (
                lowered.get("is_nullable")
                or lowered.get("nullable")
                or "YES"
            ),
            "column_default": (
                lowered.get("column_default")
                if "column_default" in lowered
                else lowered.get("data_default", lowered.get("default_expression"))
            ),
            "column_comment": (
                lowered.get("column_comment")
                or lowered.get("comment")
                or ""
            ),
            "column_key": lowered.get("column_key") or lowered.get("key") or "",
        }
        return normalized

    @staticmethod
    def _normalize_constraint_row(
        row: dict[str, Any] | tuple[Any, ...] | list[Any],
        cols: list[str],
    ) -> dict[str, Any]:
        raw = row if isinstance(row, dict) else dict(zip(cols, row, strict=False))

        lowered = {str(key).lower(): value for key, value in raw.items()}
        return {
            "constraint_name": lowered.get("constraint_name") or "",
            "constraint_type": lowered.get("constraint_type") or "",
            "column_names": lowered.get("column_names") or "",
            "referenced_table_name": lowered.get("referenced_table_name") or "",
            "referenced_column_names": lowered.get("referenced_column_names") or "",
            "check_clause": (
                lowered.get("check_clause")
                or lowered.get("search_condition")
                or lowered.get("search_condition_vc")
                or ""
            ),
        }

    @staticmethod
    def _normalize_index_row(
        row: dict[str, Any] | tuple[Any, ...] | list[Any],
        cols: list[str],
    ) -> dict[str, Any]:
        raw = row if isinstance(row, dict) else dict(zip(cols, row, strict=False))

        lowered = {str(key).lower(): value for key, value in raw.items()}
        normalized = {
            "index_name": lowered.get("index_name") or "",
            "index_type": lowered.get("index_type") or "",
            "column_names": lowered.get("column_names") or "",
            "is_composite": lowered.get("is_composite") or "NO",
            "index_comment": lowered.get("index_comment") or "",
        }
        if "index_definition" in lowered:
            normalized["index_definition"] = lowered.get("index_definition") or ""
        return normalized

    @staticmethod
    async def _load_instance(db: AsyncSession, instance_id: int) -> Instance:
        result = await db.execute(
            select(Instance)
            .options(
                selectinload(Instance.instance_tags),
                selectinload(Instance.resource_groups),
                selectinload(Instance.tunnel),
            )
            .where(Instance.id == instance_id)
        )
        inst = result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在")
        return inst

    @staticmethod
    async def list_instances(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        db_type: str | None = None,
        search: str | None = None,
        resource_group_id: int | None = None,
        user: dict | None = None,
    ) -> tuple[int, list[Instance]]:
        query = (
            select(Instance)
            .options(
                selectinload(Instance.instance_tags),
                selectinload(Instance.resource_groups),
            )
            .where(Instance.is_active)
        )
        if db_type:
            query = query.where(Instance.db_type == db_type.lower())
        if search:
            query = query.where(Instance.instance_name.ilike(f"%{search}%"))
        if resource_group_id:
            from app.models.user import instance_resource_group

            query = query.join(
                instance_resource_group,
                Instance.id == instance_resource_group.c.instance_id,
            ).where(instance_resource_group.c.resource_group_id == resource_group_id)

        if user and not (
            user.get("is_superuser") or "query_all_instances" in user.get("permissions", [])
        ):
            user_rg_ids = user.get("resource_groups", [])
            if not user_rg_ids:
                return 0, []
            from app.models.user import instance_resource_group

            query = query.join(
                instance_resource_group,
                Instance.id == instance_resource_group.c.instance_id,
            ).where(instance_resource_group.c.resource_group_id.in_(user_rg_ids))
            query = query.distinct()

        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar_one()

        query = (
            query.order_by(Instance.instance_name).offset((page - 1) * page_size).limit(page_size)
        )
        result = await db.execute(query)
        return total, list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, instance_id: int) -> Instance:
        return await InstanceService._load_instance(db, instance_id)

    @staticmethod
    async def create(db: AsyncSession, data: InstanceCreate) -> Instance:
        # 检查实例名唯一性
        existing = await db.execute(
            select(Instance).where(Instance.instance_name == data.instance_name)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"实例名 '{data.instance_name}' 已存在")

        inst = Instance(
            instance_name=data.instance_name,
            type=data.type,
            db_type=data.db_type,
            mode=data.mode,
            host=data.host,
            port=data.port,
            # 密码加密存储（修复 P0-2 相关的密码明文问题）
            user=encrypt_field(data.user),
            password=encrypt_field(data.password),
            is_ssl=data.is_ssl,
            db_name=data.db_name,
            show_db_name_regex=data.show_db_name_regex,
            remark=data.remark,
            tunnel_id=data.tunnel_id,
        )
        db.add(inst)
        await db.flush()

        # 关联资源组
        if data.resource_group_ids:
            result = await db.execute(
                select(ResourceGroup).where(ResourceGroup.id.in_(data.resource_group_ids))
            )
            inst.resource_groups = list(result.scalars().all())

        # 标签
        for key, value in data.tags.items():
            tag = InstanceTag(tag_key=key, tag_value=value, instance_id=inst.id)
            db.add(tag)

        await db.commit()
        # 重新查询，确保所有关系都已预加载（避免 greenlet_spawn 错误）
        inst = await InstanceService._load_instance(db, inst.id)
        logger.info("instance_created")
        return inst

    @staticmethod
    async def update(db: AsyncSession, instance_id: int, data: InstanceUpdate) -> Instance:
        inst = await InstanceService._load_instance(db, instance_id)

        update_fields = data.model_dump(exclude_none=True, exclude={"resource_group_ids", "tags"})

        # 密码字段需要加密
        if "user" in update_fields:
            update_fields["user"] = encrypt_field(update_fields["user"])
        if "password" in update_fields:
            update_fields["password"] = encrypt_field(update_fields["password"])

        for field, value in update_fields.items():
            setattr(inst, field, value)

        if data.resource_group_ids is not None:
            result = await db.execute(
                select(ResourceGroup).where(ResourceGroup.id.in_(data.resource_group_ids))
            )
            inst.resource_groups = list(result.scalars().all())

        if data.tags is not None:
            # 清除旧标签重新写入
            for tag in inst.instance_tags:
                await db.delete(tag)
            for key, value in data.tags.items():
                db.add(InstanceTag(tag_key=key, tag_value=value, instance_id=inst.id))

        await db.commit()
        inst = await InstanceService._load_instance(db, inst.id)
        return inst

    @staticmethod
    async def delete(db: AsyncSession, instance_id: int) -> None:
        inst = await InstanceService._load_instance(db, instance_id)
        if inst.resource_groups:
            rg_names = "、".join(rg.group_name_cn or rg.group_name for rg in inst.resource_groups)
            raise ConflictException(
                f"实例已被资源组 {rg_names} 关联，请到资源组管理中移除该实例后再删除"
            )
        # 软删除（标记为 inactive）
        inst.is_active = False
        await db.commit()

    @staticmethod
    async def test_connection(db: AsyncSession, instance_id: int) -> dict:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        rs = await engine.test_connection()
        return {
            "success": rs.is_success,
            "message": rs.error if not rs.is_success else "连接成功",
            "cost_time_ms": rs.cost_time,
        }

    @staticmethod
    async def get_databases(db: AsyncSession, instance_id: int) -> list[str]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        rs = await engine.get_all_databases()
        if not rs.is_success:
            raise Exception(f"获取数据库列表失败：{rs.error}")
        result = []
        for row in rs.rows:
            if isinstance(row, dict):
                result.append(str(list(row.values())[0]))
            elif isinstance(row, (tuple, list)):
                result.append(str(row[0]))
            else:
                result.append(str(row))
        return result

    @staticmethod
    async def get_tables(db: AsyncSession, instance_id: int, db_name: str) -> list[str]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        rs = await engine.get_all_tables(db_name=db_name)
        if not rs.is_success:
            raise Exception(f"获取表列表失败：{rs.error}")
        result = []
        for row in rs.rows:
            if isinstance(row, dict):
                result.append(str(list(row.values())[0]))
            elif isinstance(row, (tuple, list)):
                result.append(str(row[0]))
            else:
                result.append(str(row))
        return result

    @staticmethod
    async def get_columns(
        db: AsyncSession, instance_id: int, db_name: str, tb_name: str
    ) -> list[dict]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        resolved_table_name, extra_kwargs = InstanceService._resolve_table_lookup(
            inst, db_name, tb_name
        )
        rs = await engine.get_all_columns_by_tb(
            db_name=db_name,
            tb_name=resolved_table_name,
            **extra_kwargs,
        )
        if not rs.is_success:
            raise Exception(f"获取列信息失败：{rs.error}")
        cols = rs.column_list or []
        return [InstanceService._normalize_column_row(row, cols) for row in rs.rows]

    @staticmethod
    async def get_constraints(
        db: AsyncSession, instance_id: int, db_name: str, tb_name: str
    ) -> list[dict]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        getter = getattr(engine, "get_table_constraints", None)
        if getter is None:
            return []

        resolved_table_name, extra_kwargs = InstanceService._resolve_table_lookup(
            inst, db_name, tb_name
        )
        rs = await getter(db_name=db_name, tb_name=resolved_table_name, **extra_kwargs)
        if not rs.is_success:
            raise Exception(f"获取约束信息失败：{rs.error}")
        cols = rs.column_list or []
        constraints = [
            InstanceService._normalize_constraint_row(row, cols) for row in rs.rows
        ]
        return [
            constraint
            for constraint in constraints
            if not InstanceService._should_hide_column_not_null_check(constraint)
        ]

    @staticmethod
    async def get_indexes(
        db: AsyncSession, instance_id: int, db_name: str, tb_name: str
    ) -> list[dict]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        getter = getattr(engine, "get_table_indexes", None)
        if getter is None:
            return []

        resolved_table_name, extra_kwargs = InstanceService._resolve_table_lookup(inst, db_name, tb_name)
        rs = await getter(db_name=db_name, tb_name=resolved_table_name, **extra_kwargs)
        if not rs.is_success:
            raise Exception(f"获取索引信息失败：{rs.error}")
        cols = rs.column_list or []
        indexes = [InstanceService._normalize_index_row(row, cols) for row in rs.rows]
        for index in indexes:
            index.setdefault("index_definition", "")
        return indexes

    @staticmethod
    async def get_table_ddl(
        db: AsyncSession, instance_id: int, db_name: str, tb_name: str
    ) -> dict[str, str | None]:
        inst = await InstanceService._load_instance(db, instance_id)
        resolved_table_name, extra_kwargs = InstanceService._resolve_table_lookup(
            inst, db_name, tb_name
        )
        engine = get_engine(inst)
        source = "generated"
        ddl = ""
        raw_ddl = ""
        columns: list[dict[str, Any]] = []
        constraints: list[dict[str, Any]] = []
        indexes: list[dict[str, Any]] = []

        try:
            rs = await engine.describe_table(
                db_name=db_name,
                tb_name=resolved_table_name,
                **extra_kwargs,
            )
            if rs.is_success and rs.rows:
                lowered_columns = [str(col).lower() for col in (rs.column_list or [])]
                if "create table" in lowered_columns:
                    create_idx = lowered_columns.index("create table")
                    first_row = rs.rows[0]
                    if isinstance(first_row, dict):
                        ddl = str(first_row.get(rs.column_list[create_idx], "")).strip()
                    elif isinstance(first_row, (tuple, list)) and len(first_row) > create_idx:
                        ddl = str(first_row[create_idx]).strip()
                    source = "engine"
                    raw_ddl = ddl
                elif inst.db_type in {"mysql", "tidb", "starrocks"} and len(rs.rows[0]) >= 2:
                    first_row = rs.rows[0]
                    if isinstance(first_row, (tuple, list)):
                        ddl = str(first_row[1]).strip()
                        source = "engine"
                        raw_ddl = ddl
        except Exception:
            ddl = ""

        if not ddl:
            try:
                columns = await InstanceService.get_columns(
                    db, instance_id, db_name, tb_name
                )
            except Exception:
                columns = []
            try:
                constraints = await InstanceService.get_constraints(
                    db, instance_id, db_name, tb_name
                )
            except Exception:
                constraints = []
            try:
                indexes = await InstanceService.get_indexes(
                    db, instance_id, db_name, tb_name
                )
            except Exception:
                indexes = []
            ddl = InstanceService._build_generic_table_ddl(
                inst,
                tb_name,
                columns,
                constraints,
                indexes,
            )
            source = "generated"
            raw_ddl = ddl

        copyable_ddl = ddl
        if inst.db_type == "oracle":
            if not columns:
                try:
                    columns = await InstanceService.get_columns(
                        db, instance_id, db_name, tb_name
                    )
                except Exception:
                    columns = []
            oracle_comment_lines = InstanceService._build_comment_statements(
                inst,
                resolved_table_name,
                columns,
                schema_name=db_name,
            )
            if oracle_comment_lines and not all(
                line in (raw_ddl or ddl) for line in oracle_comment_lines
            ):
                raw_ddl = f"{(raw_ddl or ddl).rstrip()}\n\n" + "\n".join(oracle_comment_lines)
            copyable_ddl = InstanceService._simplify_oracle_ddl(raw_ddl or ddl)

        return {
            "table_name": tb_name,
            "ddl": copyable_ddl,
            "copyable_ddl": copyable_ddl,
            "raw_ddl": raw_ddl or ddl,
            "source": source,
        }

    @staticmethod
    async def get_variables(db: AsyncSession, instance_id: int) -> list[dict]:
        inst = await InstanceService._load_instance(db, instance_id)
        engine = get_engine(inst)
        rs = await engine.get_variables()
        if not rs.is_success:
            raise Exception(f"获取参数列表失败：{rs.error}")
        cols = rs.column_list or []
        return [
            dict(zip(cols, row, strict=False)) if isinstance(row, (tuple, list)) else row
            for row in rs.rows
        ]

    # ─── 实例信息序列化（不暴露密码）────────────────────────
    @staticmethod
    def to_response(inst: Instance) -> dict:
        return {
            "id": inst.id,
            "instance_name": inst.instance_name,
            "type": inst.type,
            "db_type": inst.db_type,
            "mode": inst.mode,
            "host": inst.host,
            "port": inst.port,
            "user": decrypt_field(inst.user),  # 用户名可见，密码不返回
            "is_ssl": inst.is_ssl,
            "db_name": inst.db_name,
            "show_db_name_regex": inst.show_db_name_regex,
            "remark": inst.remark,
            "is_active": inst.is_active,
            "tunnel_id": inst.tunnel_id,
            "resource_group_ids": [rg.id for rg in inst.resource_groups],
            "tags": {t.tag_key: t.tag_value for t in inst.instance_tags},
            "tenant_id": inst.tenant_id,
        }


# ══════════════════════════════════════════════════════════════
# TunnelService
# ══════════════════════════════════════════════════════════════


class TunnelService:
    @staticmethod
    async def list_tunnels(db: AsyncSession) -> list[SshTunnel]:
        result = await db.execute(select(SshTunnel))
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: TunnelCreate) -> SshTunnel:
        existing = await db.execute(
            select(SshTunnel).where(SshTunnel.tunnel_name == data.tunnel_name)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"SSH 隧道 '{data.tunnel_name}' 已存在")

        tunnel = SshTunnel(
            tunnel_name=data.tunnel_name,
            host=data.host,
            port=data.port,
            user=data.user,
            password=encrypt_field(data.password) if data.password else None,
            private_key=encrypt_field(data.private_key) if data.private_key else None,
            private_key_password=encrypt_field(data.private_key_password)
            if data.private_key_password
            else None,
        )
        db.add(tunnel)
        await db.commit()
        await db.refresh(tunnel)
        return tunnel

    @staticmethod
    async def delete(db: AsyncSession, tunnel_id: int) -> None:
        result = await db.execute(select(SshTunnel).where(SshTunnel.id == tunnel_id))
        tunnel = result.scalar_one_or_none()
        if not tunnel:
            raise NotFoundException(f"SSH 隧道 ID={tunnel_id} 不存在")
        await db.delete(tunnel)
        await db.commit()
