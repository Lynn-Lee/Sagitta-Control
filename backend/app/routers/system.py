"""系统管理聚合路由。"""

from fastapi import APIRouter

from app.routers.system_routes import (
    access_control,
    audit_init,
    commercial_delivery,
    config_notifications,
    license,
    users,
)

router = APIRouter()

for sub_router in (
    users.router,
    access_control.router,
    config_notifications.router,
    license.router,
    commercial_delivery.router,
    audit_init.router,
):
    router.include_router(sub_router)
