"""系统访问控制子路由。"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 权限码
# ═══════════════════════════════════════════════════════════


@router.get("/permissions/", summary="权限码列表")
async def list_permissions(db: AsyncSession = Depends(get_db), _user=Depends(current_user)):

    from app.models.user import Permission

    result = await db.execute(select(Permission).order_by(Permission.codename))
    perms = result.scalars().all()
    return {"permissions": [{"codename": p.codename, "name": p.name} for p in perms]}
