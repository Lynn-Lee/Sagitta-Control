"""
实例数据库注册服务（Pack C2）。
管理每个实例下已注册的数据库列表，支持手动维护和从引擎自动同步。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.engines.registry import get_engine
from app.models.instance import Instance, InstanceDatabase

logger = logging.getLogger(__name__)

# Oracle 用 Schema，Redis 用编号，其他用 Database
DB_NAME_LABEL = {
    "oracle": "Schema",
    "redis": "数据库编号",
    "elasticsearch": "索引前缀",
}


class InstanceDatabaseService:
    @staticmethod
    def get_db_label(db_type: str) -> str:
        """根据数据库类型返回数据库名的 label。"""
        return DB_NAME_LABEL.get(db_type, "数据库")

    @staticmethod
    async def list_databases(
        db: AsyncSession,
        instance_id: int,
        include_inactive: bool = False,
    ) -> list[dict]:
        """获取实例下已注册的数据库列表。"""
        stmt = select(InstanceDatabase).where(InstanceDatabase.instance_id == instance_id)
        if not include_inactive:
            stmt = stmt.where(InstanceDatabase.is_active)
        stmt = stmt.order_by(InstanceDatabase.db_name)
        result = await db.execute(stmt)
        rows = result.scalars().all()

        # 获取实例 db_type 用于返回 label
        inst_result = await db.execute(select(Instance).where(Instance.id == instance_id))
        inst = inst_result.scalar_one_or_none()
        label = InstanceDatabaseService.get_db_label(inst.db_type if inst else "")

        return [
            {
                "id": r.id,
                "db_name": r.db_name,
                "remark": r.remark,
                "is_active": r.is_active,
                "sync_at": r.sync_at.isoformat() if r.sync_at else None,
                "db_name_label": label,
            }
            for r in rows
        ]

    @staticmethod
    async def add_database(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        remark: str = "",
    ) -> InstanceDatabase:
        """手动添加一个数据库。"""
        inst = await db.execute(select(Instance).where(Instance.id == instance_id))
        if not inst.scalar_one_or_none():
            raise NotFoundException(f"实例 ID={instance_id} 不存在")

        # 检查是否已存在
        existing = await db.execute(
            select(InstanceDatabase).where(
                and_(
                    InstanceDatabase.instance_id == instance_id,
                    InstanceDatabase.db_name == db_name,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"数据库 '{db_name}' 已存在于此实例")

        idb = InstanceDatabase(
            instance_id=instance_id,
            db_name=db_name.strip(),
            remark=remark,
            is_active=True,
        )
        db.add(idb)
        await db.commit()
        await db.refresh(idb)
        logger.info("instance_db_added: instance=%s db=%s", instance_id, db_name)
        return idb

    @staticmethod
    async def update_database(
        db: AsyncSession,
        idb_id: int,
        remark: str | None = None,
        is_active: bool | None = None,
    ) -> InstanceDatabase:
        result = await db.execute(select(InstanceDatabase).where(InstanceDatabase.id == idb_id))
        idb = result.scalar_one_or_none()
        if not idb:
            raise NotFoundException(f"记录 ID={idb_id} 不存在")
        if remark is not None:
            idb.remark = remark
        if is_active is not None:
            idb.is_active = is_active
        await db.commit()
        await db.refresh(idb)
        return idb

    @staticmethod
    async def delete_database(db: AsyncSession, idb_id: int) -> None:
        result = await db.execute(select(InstanceDatabase).where(InstanceDatabase.id == idb_id))
        idb = result.scalar_one_or_none()
        if not idb:
            raise NotFoundException(f"记录 ID={idb_id} 不存在")
        await db.delete(idb)
        await db.commit()

    @staticmethod
    async def sync_from_engine(
        db: AsyncSession,
        instance_id: int,
    ) -> dict:
        """
        连接引擎拉取数据库列表，自动同步到 instance_database 表。
        与当前连接用户的真实可见范围保持一致：
        - 新可见的新增
        - 仍可见的更新时间
        - 当前已不可见的旧记录删除
        返回同步结果统计。
        """
        inst_result = await db.execute(
            select(Instance).where(Instance.id == instance_id, Instance.is_active)
        )
        inst = inst_result.scalar_one_or_none()
        if not inst:
            raise NotFoundException(f"实例 ID={instance_id} 不存在或已停用")

        engine = get_engine(inst)
        now = datetime.now(UTC)

        # 根据数据库类型调用不同的查询方式
        try:
            if inst.db_type == "redis":
                # Redis 固定返回 0-15
                db_list = [str(i) for i in range(16)]
            else:
                rs = await engine.get_all_databases()
                if rs.error:
                    return {
                        "success": False,
                        "message": f"连接失败：{rs.error}",
                        "added": 0,
                        "skipped": 0,
                    }
                db_list = [
                    str(list(row.values())[0])
                    if isinstance(row, dict)
                    else str(row[0])
                    if isinstance(row, (tuple, list))
                    else str(row)
                    for row in rs.rows
                ]
        except Exception as e:
            return {
                "success": False,
                "message": f"查询失败：{str(e)}",
                "added": 0,
                "skipped": 0,
            }

        # 查已有记录
        existing_result = await db.execute(
            select(InstanceDatabase).where(InstanceDatabase.instance_id == instance_id)
        )
        existing_rows = existing_result.scalars().all()
        existing_by_name = {row.db_name: row for row in existing_rows}
        visible_names = {db_name for db_name in db_list if db_name}

        added = 0
        updated = 0
        removed = 0

        for db_name, existing in existing_by_name.items():
            if db_name not in visible_names:
                await db.delete(existing)
                removed += 1

        for db_name in db_list:
            if not db_name:
                continue
            existing = existing_by_name.get(db_name)
            if existing:
                existing.sync_at = now
                # 兼容旧版本曾将部分库/Schema 自动置为“系统库（默认禁用）”
                if existing.remark == "系统库（默认禁用）":
                    existing.remark = ""
                    existing.is_active = True
                updated += 1
            else:
                db.add(
                    InstanceDatabase(
                        instance_id=instance_id,
                        db_name=db_name,
                        remark="",
                        is_active=True,
                        sync_at=now,
                    )
                )
                added += 1

        await db.commit()
        logger.info(
            "instance_db_synced: instance=%s added=%d updated=%d removed=%d",
            instance_id,
            added,
            updated,
            removed,
        )
        return {
            "success": True,
            "message": f"同步完成：新增 {added} 个，更新 {updated} 个，移除 {removed} 个",
            "added": added,
            "updated": updated,
            "removed": removed,
            "total": len(db_list),
        }
