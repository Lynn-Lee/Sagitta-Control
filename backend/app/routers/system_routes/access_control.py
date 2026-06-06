"""访问控制聚合路由。"""

from fastapi import APIRouter

from app.routers.system_routes.access_control_routes import (
    permissions,
    resource_groups,
    roles,
    user_groups,
)

router = APIRouter()

for sub_router in (
    roles.router,
    user_groups.router,
    resource_groups.router,
    permissions.router,
):
    router.include_router(sub_router)
