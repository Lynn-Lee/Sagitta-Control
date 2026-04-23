"""
实例管理 Pydantic Schema。
"""

from pydantic import BaseModel, field_validator

# ─── SSH 隧道 ─────────────────────────────────────────────────

class TunnelCreate(BaseModel):
    tunnel_name: str
    host: str
    port: int = 22
    user: str
    password: str | None = None
    private_key: str | None = None
    private_key_password: str | None = None

    @field_validator("port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("端口号必须在 1-65535 之间")
        return v


class TunnelResponse(BaseModel):
    id: int
    tunnel_name: str
    host: str
    port: int
    user: str
    tenant_id: int

    model_config = {"from_attributes": True}


# ─── 实例 ─────────────────────────────────────────────────────

DB_TYPES = [
    "mysql", "tidb", "pgsql", "oracle", "mongo", "redis",
    "clickhouse", "elasticsearch", "opensearch",
    "mssql", "cassandra", "doris",
]


class InstanceCreate(BaseModel):
    instance_name: str
    type: str = "master"
    db_type: str
    mode: str = "standalone"
    host: str
    port: int
    user: str
    password: str
    is_ssl: bool = False
    db_name: str = ""
    show_db_name_regex: str = ""
    remark: str = ""
    tunnel_id: int | None = None
    resource_group_ids: list[int] = []
    tags: dict[str, str] = {}

    @field_validator("db_type")
    @classmethod
    def db_type_valid(cls, v: str) -> str:
        if v.lower() not in DB_TYPES:
            raise ValueError(f"不支持的数据库类型：{v}，支持：{', '.join(DB_TYPES)}")
        return v.lower()

    @field_validator("type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in ("master", "slave"):
            raise ValueError("type 必须是 master 或 slave")
        return v

    @field_validator("port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("端口号必须在 1-65535 之间")
        return v


class InstanceUpdate(BaseModel):
    instance_name: str | None = None
    type: str | None = None
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    is_ssl: bool | None = None
    db_name: str | None = None
    show_db_name_regex: str | None = None
    remark: str | None = None
    tunnel_id: int | None = None
    resource_group_ids: list[int] | None = None
    tags: dict[str, str] | None = None
    is_active: bool | None = None


class InstanceTagResponse(BaseModel):
    tag_key: str
    tag_value: str

    model_config = {"from_attributes": True}


class InstanceResponse(BaseModel):
    id: int
    instance_name: str
    type: str
    db_type: str
    mode: str
    host: str
    port: int
    user: str          # 返回时已脱敏（不返回密码）
    is_ssl: bool
    db_name: str
    show_db_name_regex: str
    remark: str
    is_active: bool
    tunnel_id: int | None
    resource_group_ids: list[int] = []
    tags: dict[str, str] = {}
    tenant_id: int

    model_config = {"from_attributes": True}


class InstanceListResponse(BaseModel):
    total: int
    items: list[InstanceResponse]


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    cost_time_ms: int = 0


class DatabaseListResponse(BaseModel):
    databases: list[str]


class TableListResponse(BaseModel):
    tables: list[str]


class TableDDLResponse(BaseModel):
    table_name: str
    ddl: str
    copyable_ddl: str | None = None
    raw_ddl: str | None = None
    source: str = "generated"


class ColumnInfo(BaseModel):
    column_name: str
    column_type: str
    is_nullable: str
    column_default: str | None
    column_comment: str = ""
    column_key: str = ""


class ColumnListResponse(BaseModel):
    columns: list[ColumnInfo]


class ParamItem(BaseModel):
    variable_name: str
    value: str


class ParamListResponse(BaseModel):
    params: list[ParamItem]


class SetParamRequest(BaseModel):
    variable_name: str
    variable_value: str
