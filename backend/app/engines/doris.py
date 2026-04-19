"""Engine skeleton - Sprint 2/4 will implement fully."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.engines.models import ResultSet, ReviewSet

if TYPE_CHECKING:
    from app.models.instance import Instance

class DorisEngine:
    name = "SkeletonEngine"
    db_type = "doris"
    def __init__(self, instance: Instance) -> None:
        self.instance = instance
    async def get_connection(self, db_name=None): raise NotImplementedError("Sprint 2/4")
    async def test_connection(self) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    def escape_string(self, value: str) -> str: return value
    async def get_all_databases(self) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    async def get_all_tables(self, db_name: str, **kw: Any) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    async def get_all_columns_by_tb(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    async def describe_table(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    async def get_tables_metas_data(self, db_name: str, **kw: Any) -> list: return []
    async def get_table_constraints(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet: return ResultSet()
    async def get_table_indexes(self, db_name: str, tb_name: str, **kw: Any) -> ResultSet: return ResultSet()
    def query_check(self, db_name: str, sql: str) -> dict: return {"msg": "", "syntax_error": False}
    def filter_sql(self, sql: str, limit_num: int) -> str: return sql
    async def query(self, db_name: str, sql: str, limit_num: int = 0, parameters: dict | None = None, **kw: Any) -> ResultSet: return ResultSet(error="Sprint 2/4 实现")
    def query_masking(self, db_name: str, sql: str, resultset: ResultSet) -> ResultSet: return resultset
    async def execute_check(self, db_name: str, sql: str) -> ReviewSet: return ReviewSet(full_sql=sql, error="Sprint 2/4 实现")
    async def execute(self, db_name: str, sql: str, **kw: Any) -> ReviewSet: return ReviewSet(full_sql=sql, error="Sprint 2/4 实现")
    async def execute_workflow(self, workflow: Any) -> ReviewSet: return ReviewSet(error="Sprint 2/4 实现")
    async def collect_metrics(self) -> dict: return {"health": {"up": 0}}
    def get_supported_metric_groups(self) -> list: return ["health"]
