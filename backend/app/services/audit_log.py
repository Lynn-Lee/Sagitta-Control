"""
操作审计日志服务（Pack C1）。
"""
from __future__ import annotations

import logging
from datetime import UTC

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import OperationLog

logger = logging.getLogger(__name__)


class AuditLogService:

    @staticmethod
    async def write(
        db: AsyncSession,
        user: dict,
        action: str,
        module: str,
        detail: str = "",
        result: str = "success",
        request: Request | None = None,
        remark: str = "",
    ) -> None:
        """写入一条操作日志。"""
        ip = ""
        if request:
            forwarded = request.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0].strip() if forwarded else (
                request.client.host if request.client else ""
            )

        log = OperationLog(
            user_id=user.get("id", 0),
            username=user.get("username", ""),
            action=action,
            module=module,
            detail=detail[:2000],
            ip_address=ip,
            result=result,
            remark=remark,
        )
        db.add(log)
        try:
            await db.commit()
        except Exception as e:
            logger.warning("audit_log_write_failed: %s", str(e))
            await db.rollback()

    @staticmethod
    async def list_logs(
        db: AsyncSession,
        username: str | None = None,
        module: str | None = None,
        action: str | None = None,
        result: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[OperationLog]]:
        from datetime import datetime, timedelta

        from sqlalchemy import and_

        conditions = []

        if username:
            conditions.append(OperationLog.username.ilike(f"%{username}%"))
        if module:
            conditions.append(OperationLog.module == module)
        if action:
            conditions.append(OperationLog.action.ilike(f"%{action}%"))
        if result:
            conditions.append(OperationLog.result == result)
        if date_start:
            try:
                ds = datetime.fromisoformat(date_start).replace(tzinfo=UTC)
                conditions.append(OperationLog.created_at >= ds)
            except ValueError:
                pass
        if date_end:
            try:
                de = datetime.fromisoformat(date_end).replace(tzinfo=UTC) + timedelta(days=1)
                conditions.append(OperationLog.created_at < de)
            except ValueError:
                pass

        count_stmt = select(func.count()).select_from(OperationLog)
        data_stmt = select(OperationLog)

        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
            data_stmt = data_stmt.where(and_(*conditions))

        total = (await db.execute(count_stmt)).scalar_one()
        data_stmt = data_stmt.order_by(OperationLog.created_at.desc())
        data_stmt = data_stmt.offset((page - 1) * page_size).limit(page_size)
        result_rows = await db.execute(data_stmt)

        return total, list(result_rows.scalars().all())

    @staticmethod
    def get_modules() -> list[str]:
        return ["auth", "workflow", "query", "instance", "user", "system", "monitor", "session"]
