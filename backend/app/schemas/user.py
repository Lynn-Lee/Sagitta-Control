"""
用户与资源组 Pydantic Schema。
"""

from pydantic import BaseModel, field_validator

from app.core.security import validate_password_strength

# ─── 用户 ─────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""
    phone: str = ""
    is_superuser: bool = False
    role_id: int | None = None
    manager_id: int | None = None
    employee_id: str = ""
    department: str = ""
    title: str = ""
    user_group_ids: list[int] = []

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("用户名至少 2 个字符")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    role_id: int | None = None
    manager_id: int | None = None
    employee_id: str | None = None
    department: str | None = None
    title: str | None = None
    user_group_ids: list[int] | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    email: str
    phone: str
    is_active: bool
    is_superuser: bool
    auth_type: str
    totp_enabled: bool
    tenant_id: int
    user_groups: list[int] = []

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    total: int
    items: list[UserResponse]


class GrantPermissionRequest(BaseModel):
    permission_codes: list[str]


# ─── 资源组 ───────────────────────────────────────────────────


class ResourceGroupCreate(BaseModel):
    group_name: str
    group_name_cn: str = ""
    instance_ids: list[int] = []
    user_group_ids: list[int] = []

    @field_validator("group_name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("资源组名称至少 2 个字符")
        return v


class ResourceGroupUpdate(BaseModel):
    group_name_cn: str | None = None
    is_active: bool | None = None
    instance_ids: list[int] | None = None
    user_group_ids: list[int] | None = None


class ResourceGroupResponse(BaseModel):
    id: int
    group_name: str
    group_name_cn: str
    ding_webhook: str
    feishu_webhook: str
    is_active: bool
    tenant_id: int
    member_count: int = 0
    instance_count: int = 0

    model_config = {"from_attributes": True}


class ResourceGroupListResponse(BaseModel):
    total: int
    items: list[ResourceGroupResponse]
