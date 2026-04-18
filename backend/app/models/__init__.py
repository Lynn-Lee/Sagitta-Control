"""
统一导出所有模型，供 Alembic autogenerate 使用。
新增模型后记得在这里 import。
"""

from app.models.base import Base, BaseModel  # noqa: F401
from app.models.approval_flow import ApprovalFlow, ApprovalFlowNode  # noqa: F401
from app.models.instance import Instance, InstanceDatabase, InstanceTag, SshTunnel  # noqa: F401
from app.models.masking import MaskingRule, WorkflowTemplate  # noqa: F401
from app.models.monitor import (  # noqa: F401
    MonitorCollectConfig,
    MonitorPrivilege,
    MonitorPrivilegeApply,
)
from app.models.query import QueryLog, QueryPrivilege, QueryPrivilegeApply  # noqa: F401
from app.models.role import Role, UserGroup  # noqa: F401
from app.models.system import OperationLog, SystemConfig  # noqa: F401
from app.models.user import Permission, ResourceGroup, Users  # noqa: F401
from app.models.workflow import (  # noqa: F401
    AuditStatus,
    SqlWorkflow,
    SqlWorkflowContent,
    WorkflowAudit,
    WorkflowLog,
    WorkflowStatus,
    WorkflowType,
)

__all__ = [
    "Base",
    "BaseModel",
    "Users",
    "ResourceGroup",
    "Permission",
    "Role",
    "UserGroup",
    "Instance",
    "ApprovalFlow",
    "ApprovalFlowNode",
    "SshTunnel",
    "InstanceTag",
    "InstanceDatabase",
    "SqlWorkflow",
    "SqlWorkflowContent",
    "WorkflowAudit",
    "WorkflowLog",
    "WorkflowStatus",
    "WorkflowType",
    "AuditStatus",
    "QueryPrivilege",
    "QueryPrivilegeApply",
    "QueryLog",
    "MonitorCollectConfig",
    "MonitorPrivilegeApply",
    "MonitorPrivilege",
    "SystemConfig",
    "OperationLog",
    "MaskingRule",
    "WorkflowTemplate",
]
