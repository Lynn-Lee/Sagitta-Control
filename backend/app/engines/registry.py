"""
引擎注册工厂。
通过 get_engine(instance) 根据 db_type 分发到对应引擎实现。
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.instance import Instance

logger = logging.getLogger(__name__)

# 引擎注册表：db_type → 引擎类（延迟导入，避免循环依赖）
_REGISTRY: dict[str, str] = {
    "mysql":         "app.engines.mysql:MysqlEngine",
    "tidb":          "app.engines.mysql:MysqlEngine",
    "starrocks":     "app.engines.starrocks:StarRocksEngine",
    "pgsql":         "app.engines.pgsql:PgSQLEngine",
    "oracle":        "app.engines.oracle:OracleEngine",
    "mongo":         "app.engines.mongo:MongoEngine",
    "redis":         "app.engines.redis:RedisEngine",
    "clickhouse":    "app.engines.clickhouse:ClickHouseEngine",
    "elasticsearch": "app.engines.elasticsearch:ElasticsearchEngine",
    "opensearch":    "app.engines.elasticsearch:OpenSearchEngine",
    "mssql":         "app.engines.mssql:MssqlEngine",
    "cassandra":     "app.engines.cassandra:CassandraEngine",
    "doris":         "app.engines.doris:DorisEngine",
}


def get_engine(instance: "Instance"):
    """
    根据实例的 db_type 返回对应引擎实例。
    移除了 isinstance(EngineProtocol) 运行时检查——
    typing.Protocol 的 runtime_checkable 只检查方法名存在，
    不检查方法签名，会误判正确实现的引擎。
    """
    db_type = instance.db_type.lower()
    engine_path = _REGISTRY.get(db_type)

    if not engine_path:
        raise ValueError(
            f"不支持的数据库类型：{db_type}。"
            f"已支持：{', '.join(_REGISTRY.keys())}"
        )

    module_path, class_name = engine_path.rsplit(":", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        engine_class = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        logger.error("engine_import_failed: %s", str(e))
        raise ValueError(f"加载引擎失败：{db_type} → {e}") from e

    engine = engine_class(instance=instance)
    logger.debug("engine_created: %s for %s", class_name, db_type)
    return engine


def register_engine(db_type: str, engine_path: str) -> None:
    """注册自定义引擎（扩展点）。"""
    _REGISTRY[db_type.lower()] = engine_path
    logger.info("engine_registered: %s", db_type)


def supported_engines() -> list[str]:
    """返回当前支持的数据库类型列表。"""
    return list(_REGISTRY.keys())
