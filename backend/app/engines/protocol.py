"""
引擎协议定义（替代 Archery 1.x 的 EngineBase 隐式鸭子类型）。

使用 Python typing.Protocol 实现结构化子类型：
- 所有引擎只需实现 Protocol 中声明的方法，无需继承
- mypy / pyright 可在 CI 阶段静态检查接口一致性
- 可选能力（processlist / get_rollback 等）有默认实现，引擎按需 override
"""
from typing import Any, Protocol, runtime_checkable

from app.engines.models import ResultSet, ReviewSet


@runtime_checkable
class EngineProtocol(Protocol):
    """所有数据库引擎必须实现的接口契约。"""

    name: str       # 引擎名称，如 "MysqlEngine"
    db_type: str    # 数据库类型，如 "mysql"

    # ── 连接管理 ──────────────────────────────────────────────

    async def get_connection(self, db_name: str | None = None) -> Any:
        """获取数据库连接。"""
        ...

    async def test_connection(self) -> ResultSet:
        """测试连接是否正常。"""
        ...

    def escape_string(self, value: str) -> str:
        """
        转义字符串，防止 SQL 注入。
        注意：优先使用参数化查询，仅在必要时使用此方法。
        """
        ...

    # ── 元数据查询 ────────────────────────────────────────────

    async def get_all_databases(self) -> ResultSet:
        """获取实例下所有数据库名列表。"""
        ...

    async def get_all_tables(self, db_name: str, **kwargs: Any) -> ResultSet:
        """获取指定数据库下所有表名。"""
        ...

    async def get_all_columns_by_tb(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        """获取指定表的所有列信息。"""
        ...

    async def describe_table(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        """获取表结构（DDL）。"""
        ...

    async def get_tables_metas_data(
        self, db_name: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """获取数据库所有表的元数据（用于数据字典）。"""
        ...

    async def get_table_constraints(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        """获取表级约束元数据（主键/唯一键/外键等）。"""
        return ResultSet()

    async def get_table_indexes(
        self, db_name: str, tb_name: str, **kwargs: Any
    ) -> ResultSet:
        """获取表索引元数据（普通索引/联合索引/唯一索引等）。"""
        return ResultSet()

    # ── 查询 ──────────────────────────────────────────────────

    def query_check(self, db_name: str, sql: str) -> dict[str, Any]:
        """
        查询前置检查（不执行）：
        - 语法检查
        - 是否包含写操作
        - 是否超出行数限制
        返回 {"msg": "", "has_star": False, ...}
        """
        ...

    def filter_sql(self, sql: str, limit_num: int) -> str:
        """在 SQL 末尾注入 LIMIT，防止全表扫描。"""
        ...

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ResultSet:
        """
        执行查询并返回结果集。
        所有变量必须通过 parameters 传递，禁止字符串拼接（防 SQL 注入）。
        """
        ...

    def query_masking(
        self, db_name: str, sql: str, resultset: ResultSet
    ) -> ResultSet:
        """
        对查询结果进行数据脱敏。
        2.0 使用 sqlglot 解析列引用，支持所有方言（1.x 仅支持 MySQL）。
        """
        ...

    # ── SQL 审核与执行 ────────────────────────────────────────

    async def execute_check(self, db_name: str, sql: str) -> ReviewSet:
        """
        SQL 审核（不执行）：
        - 基础审核由 sqlglot 规则引擎完成
        - 若配置了 goInception，可作为可选增强
        """
        ...

    async def execute(
        self, db_name: str, sql: str, **kwargs: Any
    ) -> ReviewSet:
        """执行单条 SQL（带事务）。"""
        ...

    async def execute_workflow(self, workflow: Any) -> ReviewSet:
        """
        执行工单中的所有 SQL（逐条执行，记录进度）。
        通过 WebSocket 推送进度（在 Celery task 中调用）。
        """
        ...

    # ── 可选能力（有默认实现，引擎按需 override）──────────────

    @property
    def auto_backup(self) -> bool:
        """是否支持自动备份（执行前备份原数据）。"""
        return False

    @property
    def server_version(self) -> tuple[int, ...]:
        """数据库服务器版本号，如 (8, 0, 32)。"""
        return ()

    async def get_rollback(self, workflow: Any) -> list[str]:
        """获取回滚 SQL 列表（仅支持备份的引擎实现）。"""
        return []

    async def processlist(
        self, command_type: str = "Query", **kwargs: Any
    ) -> ResultSet:
        """获取当前活跃会话列表（会话管理功能）。"""
        return ResultSet()

    async def kill_connection(self, thread_id: int) -> ResultSet:
        """Kill 指定会话。"""
        return ResultSet()

    async def get_variables(
        self, variables: list[str] | None = None
    ) -> ResultSet:
        """获取数据库参数配置。"""
        return ResultSet()

    async def set_variable(
        self, variable_name: str, variable_value: str
    ) -> ResultSet:
        """修改数据库参数。"""
        return ResultSet()

    # ── 可观测中心（新增）────────────────────────────────────

    async def collect_metrics(self) -> dict[str, Any]:
        """
        采集数据库核心指标（用于平台内嵌监控概览）。
        主要指标由官方 Exporter + Prometheus 提供，
        此方法仅用于连通性检查。
        """
        return {"health": {"up": 0}}

    def get_supported_metric_groups(self) -> list[str]:
        """返回此引擎支持的指标分组列表（3.0 细粒度权限预留）。"""
        return ["health"]
