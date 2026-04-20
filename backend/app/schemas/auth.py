"""
认证模块 Pydantic Schema。
"""

from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_password_strength


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    password_change_required: bool = False
    password_change_token: str | None = None
    password_change_reasons: list[str] = Field(default_factory=list)
    requires_2fa: bool = False
    two_fa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TwoFAVerifyRequest(BaseModel):
    totp_code: str


class LoginTwoFAVerifyRequest(BaseModel):
    two_fa_token: str
    totp_code: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ForceChangePasswordRequest(BaseModel):
    password_change_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class LdapLoginRequest(BaseModel):
    username: str
    password: str


class SmsCodeRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("手机号格式不正确")
        return v


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


class UserMeResponse(BaseModel):
    id: int
    username: str
    display_name: str
    email: str
    is_superuser: bool
    is_active: bool
    auth_type: str
    totp_enabled: bool
    permissions: list[str]
    resource_groups: list[int]
    tenant_id: int
    password_expiring_soon: bool = False
    days_until_password_expiry: int = 0

    model_config = {"from_attributes": True}
