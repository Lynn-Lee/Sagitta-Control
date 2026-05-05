"""
数据库实例相关模型：Instance、SshTunnel、InstanceTag。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class SshTunnel(BaseModel):
    """SSH 隧道配置（用于跳板机连接）。"""
    __tablename__ = "ssh_tunnel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tunnel_name: Mapped[str] = mapped_column(String(50), unique=True, comment="隧道名称")
    host: Mapped[str] = mapped_column(String(200), comment="跳板机地址")
    port: Mapped[int] = mapped_column(Integer, default=22, comment="SSH 端口")
    user: Mapped[str] = mapped_column(String(100), comment="SSH 用户名")
    # 密码或私钥二选一，均加密存储
    password: Mapped[str | None] = mapped_column(String(500), comment="SSH 密码（加密）")
    private_key: Mapped[str | None] = mapped_column(Text, comment="SSH 私钥（加密）")
    private_key_password: Mapped[str | None] = mapped_column(String(500), comment="私钥密码（加密）")

    instances: Mapped[list["Instance"]] = relationship("Instance", back_populates="tunnel")


class InstanceTag(BaseModel):
    """实例标签（如 env=production、team=dba）。"""
    __tablename__ = "instance_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_key: Mapped[str] = mapped_column(String(50), comment="标签键")
    tag_value: Mapped[str] = mapped_column(String(200), comment="标签值")
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"), nullable=False
    )
    instance: Mapped["Instance"] = relationship("Instance", back_populates="instance_tags")

    __table_args__ = (
        Index("ix_tag_instance", "instance_id"),
        UniqueConstraint("instance_id", "tag_key", name="uq_instance_tag_key"),
    )


class Instance(BaseModel):
    """
    数据库实例配置。
    
    密码字段使用 app.core.security.encrypt_field / decrypt_field 加密存储。
    实例密码采用加密存储。
    """
    __tablename__ = "sql_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_name: Mapped[str] = mapped_column(
        String(50), unique=True, comment="实例名称（唯一）"
    )
    type: Mapped[str] = mapped_column(
        Enum("master", "slave", name="instance_type_enum"),
        default="master", comment="主从类型"
    )
    db_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="数据库类型（mysql/pgsql/oracle/...）"
    )
    mode: Mapped[str] = mapped_column(
        String(10), default="standalone", comment="部署模式（standalone/cluster）"
    )
    host: Mapped[str] = mapped_column(String(200), nullable=False, comment="主机地址")
    port: Mapped[int] = mapped_column(Integer, nullable=False, comment="端口")

    # 认证信息（加密存储，sprint 1 中用 encrypt_field 处理）
    user: Mapped[str] = mapped_column(String(200), nullable=False, comment="用户名（加密）")
    password: Mapped[str] = mapped_column(String(500), nullable=False, comment="密码（加密）")

    is_ssl: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用 SSL")
    ssl_ca: Mapped[str | None] = mapped_column(Text, comment="SSL CA 证书")

    # 默认连接的库名（部分数据库必填）
    db_name: Mapped[str] = mapped_column(String(64), default="", comment="默认数据库名")
    # 正则过滤展示哪些库名
    show_db_name_regex: Mapped[str] = mapped_column(
        String(1024), default="", comment="数据库名过滤正则"
    )

    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    # SSH 隧道（可选）
    tunnel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ssh_tunnel.id", ondelete="SET NULL"), comment="SSH隧道ID"
    )
    tunnel: Mapped[SshTunnel | None] = relationship("SshTunnel", back_populates="instances")

    # 标签
    instance_tags: Mapped[list[InstanceTag]] = relationship(
        "InstanceTag", back_populates="instance", cascade="all, delete-orphan"
    )

    # 资源组关联（多对多，通过关联表）
    resource_groups: Mapped[list["ResourceGroup"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ResourceGroup",
        secondary="instance_resource_group",
        back_populates="instances",
    )

    __table_args__ = (
        Index("ix_instance_db_type", "db_type"),
        Index("ix_instance_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Instance {self.instance_name}({self.db_type})>"


class InstanceDatabase(BaseModel):
    """
    实例下已注册的数据库/Schema 列表。
    解耦"实例连接信息"和"数据库名"，支持手动维护和自动同步。

    Oracle → db_name 存 Schema 名（用户名）
    Redis  → db_name 存数字 index（"0"~"15"）
    其他   → db_name 存真实数据库名
    """
    __tablename__ = "instance_database"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sql_instance.id", ondelete="CASCADE"),
        nullable=False, comment="所属实例"
    )
    db_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="数据库名/Schema名/Redis index"
    )
    remark: Mapped[str] = mapped_column(String(200), default="", comment="备注（如：生产订单库）")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否可用于提交工单")
    sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最后同步时间（自动同步时更新）"
    )

    __table_args__ = (
        Index("ix_instdb_instance", "instance_id"),
        UniqueConstraint("instance_id", "db_name", name="uq_instance_db_name"),
    )
