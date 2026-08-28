"""系统管理路由请求模型。"""

import re
from typing import Any

from pydantic import BaseModel, field_validator

# 与授权中心保持一致，先在本地拦掉明显错误，减少一次往返。
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_PATTERN = re.compile(r"^(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|0\d{2,3}[-\s]?\d{7,8}(?:[-\s]?\d{1,5})?)$")


def _validate_contact_email(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("请填写联系邮箱")
    if len(normalized) > 200 or not EMAIL_PATTERN.match(normalized):
        raise ValueError("联系邮箱格式不正确")
    return normalized


def _validate_contact_phone(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if not PHONE_PATTERN.match(normalized):
        raise ValueError("联系电话格式不正确，请填写国内手机号或固话")
    return normalized


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, str]


class MailTestRequest(BaseModel):
    to_email: str


class NotifyUserTestRequest(BaseModel):
    user_id: int


class LdapTestRequest(BaseModel):
    test_username: str = ""
    test_password: str = ""


class LicenseImportRequest(BaseModel):
    license: dict[str, Any] | str


class LicenseActivateRequest(BaseModel):
    activation_code: str = ""
    customer_id: str = ""


class LicenseTrialCodeRequest(BaseModel):
    contact_email: str = ""
    contact_phone: str = ""

    @field_validator("contact_email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_contact_email(value)

    @field_validator("contact_phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return _validate_contact_phone(value)


class LicenseTrialRequest(BaseModel):
    company_name: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    verification_code: str = ""

    @field_validator("contact_email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_contact_email(value)

    @field_validator("contact_phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return _validate_contact_phone(value)


class LicenseInstanceSelectionRequest(BaseModel):
    instance_ids: list[int] = []


class LicenseChallengeRequest(BaseModel):
    customer_id: str = ""


class AcceptanceRunRequest(BaseModel):
    instance_id: int | None = None
    db_name: str = ""


class RetentionPolicyUpdateRequest(BaseModel):
    values: dict[str, int]


class RetentionCleanupRequest(BaseModel):
    category: str
