"""
引擎层数据结构。
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultSet:
    """查询结果集。"""
    # 查询是否出错
    error: str = ""
    # 列名列表
    column_list: list[str] = field(default_factory=list)
    # 数据行（每行为 tuple 或 dict）
    rows: list[Any] = field(default_factory=list)
    # 总行数（分页时可能大于 len(rows)）
    affected_rows: int = 0
    # 执行耗时（毫秒）
    cost_time: int = 0
    # 警告信息
    warning: str = ""

    @property
    def is_success(self) -> bool:
        return not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "column_list": self.column_list,
            "rows": self.rows,
            "affected_rows": self.affected_rows,
            "cost_time": self.cost_time,
            "warning": self.warning,
        }


@dataclass
class SqlItem:
    """单条 SQL 的审核/执行结果。"""
    id: int = 0
    errlevel: int = 0           # 0=正常 1=警告 2=错误
    stagestatus: str = ""       # 执行阶段状态描述
    errormessage: str = "None"  # 错误/警告信息
    sql: str = ""               # 原始 SQL
    affected_rows: int = 0      # 影响行数
    sequence: str = ""          # 执行序列
    backup_dbname: str = ""     # 备份库名
    execute_time: float = 0.0   # 执行耗时（秒）
    sqlsha1: str = ""           # SQL 哈希（gh-ost / pt-osc 用）

    @property
    def is_error(self) -> bool:
        return self.errlevel == 2

    @property
    def is_warning(self) -> bool:
        return self.errlevel == 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "errlevel": self.errlevel,
            "stagestatus": self.stagestatus,
            "errormessage": self.errormessage,
            "sql": self.sql,
            "affected_rows": self.affected_rows,
            "sequence": self.sequence,
            "backup_dbname": self.backup_dbname,
            "execute_time": self.execute_time,
            "sqlsha1": self.sqlsha1,
        }


@dataclass
class ReviewSet:
    """审核/执行结果集（包含多条 SQL 的结果）。"""
    full_sql: str = ""
    rows: list[SqlItem] = field(default_factory=list)
    # 全局错误（连接失败等）
    error: str = ""
    # 警告数
    warning_count: int = 0
    # 错误数
    error_count: int = 0
    # 是否全部成功
    is_executed: bool = False

    def __post_init__(self) -> None:
        self._recount()

    def _recount(self) -> None:
        self.warning_count = sum(1 for r in self.rows if r.is_warning)
        self.error_count = sum(1 for r in self.rows if r.is_error)

    def append(self, item: SqlItem) -> None:
        self.rows.append(item)
        if item.is_warning:
            self.warning_count += 1
        if item.is_error:
            self.error_count += 1

    @property
    def is_success(self) -> bool:
        return not self.error and self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_sql": self.full_sql,
            "rows": [r.to_dict() for r in self.rows],
            "error": self.error,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "is_executed": self.is_executed,
        }
