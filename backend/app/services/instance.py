"""
实例管理业务逻辑服务。
密码字段使用 encrypt_field / decrypt_field 加密存储（修复 1.x 明文存储问题）。
"""

from __future__ import annotations

import logging

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
        rs = await engine.get_all_columns_by_tb(db_name=db_name, tb_name=tb_name)
        if not rs.is_success:
            raise Exception(f"获取列信息失败：{rs.error}")
        cols = rs.column_list or []
        return [
            dict(zip(cols, row, strict=False)) if isinstance(row, (tuple, list)) else row
            for row in rs.rows
        ]

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
