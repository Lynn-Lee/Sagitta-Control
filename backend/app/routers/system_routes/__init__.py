"""系统管理路由分组。"""

from . import access_control, audit_init, commercial_delivery, config_notifications, license, users

__all__ = [
    "access_control",
    "audit_init",
    "commercial_delivery",
    "config_notifications",
    "license",
    "users",
]
