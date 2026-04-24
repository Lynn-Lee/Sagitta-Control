"""
引擎注册工厂测试。
"""

import pytest

from app.engines.registry import get_engine, register_engine, supported_engines


class MockInstance:
    def __init__(self, db_type: str):
        self.db_type = db_type
        self.host = "localhost"
        self.port = 3306
        self.user = ""
        self.password = ""
        self.db_name = ""
        self.show_db_name_regex = ""


class TestEngineRegistry:
    def test_supported_engines_list(self):
        engines = supported_engines()
        assert "mysql" in engines
        assert "tidb" in engines
        assert "starrocks" in engines
        assert "pgsql" in engines
        assert "mongo" in engines
        assert "redis" in engines
        assert "oracle" in engines
        assert len(engines) >= 10

    def test_get_mysql_engine(self):
        instance = MockInstance("mysql")
        engine = get_engine(instance)
        assert engine.db_type == "mysql"
        assert engine.name == "MysqlEngine"

    def test_get_mongo_engine(self):
        instance = MockInstance("mongo")
        engine = get_engine(instance)
        assert engine.db_type == "mongo"

    def test_get_tidb_engine(self):
        instance = MockInstance("tidb")
        engine = get_engine(instance)
        assert engine.name == "MysqlEngine"

    def test_get_starrocks_engine(self):
        instance = MockInstance("starrocks")
        engine = get_engine(instance)
        assert engine.name == "StarRocksEngine"
        assert engine.db_type == "starrocks"

    def test_get_mssql_engine(self):
        instance = MockInstance("mssql")
        engine = get_engine(instance)
        assert engine.db_type == "mssql"

    def test_unsupported_db_type_raises(self):
        instance = MockInstance("nonexistent_db")
        with pytest.raises(ValueError, match="不支持的数据库类型"):
            get_engine(instance)

    def test_case_insensitive_lookup(self):
        """db_type 大小写不敏感。"""
        instance = MockInstance("MySQL")
        engine = get_engine(instance)
        assert engine.db_type == "mysql"

    def test_register_custom_engine(self):
        """测试自定义引擎注册扩展点。"""
        register_engine("custom_db", "app.engines.mysql:MysqlEngine")
        instance = MockInstance("custom_db")
        engine = get_engine(instance)
        assert engine is not None
