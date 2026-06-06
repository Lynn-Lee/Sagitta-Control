"""系统管理路由请求模型。"""

from pydantic import BaseModel


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
    license: dict | str


class LicenseActivateRequest(BaseModel):
    activation_code: str = ""
    customer_id: str = ""


class LicenseChallengeRequest(BaseModel):
    customer_id: str = ""


class AcceptanceRunRequest(BaseModel):
    instance_id: int | None = None
    db_name: str = ""


class RetentionPolicyUpdateRequest(BaseModel):
    values: dict[str, int]


class RetentionCleanupRequest(BaseModel):
    category: str
