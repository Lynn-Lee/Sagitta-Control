"""StarRocks 独立引擎单元测试。"""

import pytest

from app.engines.models import ResultSet
from app.engines.starrocks import StarRocksEngine


class MockInstance:
    db_type = "starrocks"
    host = "localhost"
    port = 9030
    user = ""
    password = ""
    db_name = "testdb"
    show_db_name_regex = ""


class FakeStarRocksEngine(StarRocksEngine):
    def __init__(self, responses: dict[str, ResultSet]):
        super().__init__(MockInstance())
        self.responses = responses

    async def query(
        self,
        db_name: str,
        sql: str,
        limit_num: int = 0,
        parameters: dict | None = None,
        **kwargs,
    ) -> ResultSet:
        key = sql.lower()
        for pattern, response in self.responses.items():
            if pattern in key:
                return response
        return ResultSet(rows=[{"ok": 1}], column_list=["ok"], affected_rows=1)


class TestStarRocksQueryCheck:
    def setup_method(self):
        self.engine = StarRocksEngine(MockInstance())

    def test_select_star_warning(self):
        result = self.engine.query_check("testdb", "SELECT * FROM orders")
        assert result["has_star"] is True
        assert result["syntax_error"] is False

    def test_show_is_allowed_for_query_surface(self):
        result = self.engine.query_check("testdb", "SHOW TABLES")
        assert result["msg"] == ""
        assert result["syntax_error"] is False

    def test_write_operation_blocked_in_query_surface(self):
        result = self.engine.query_check("testdb", "INSERT INTO orders VALUES (1)")
        assert "不允许" in result["msg"]

    def test_adds_limit_to_select(self):
        assert self.engine.filter_sql("SELECT id FROM orders", 100).endswith("LIMIT 100")

    def test_does_not_add_limit_to_show(self):
        assert self.engine.filter_sql("SHOW TABLES", 100) == "SHOW TABLES"


class TestStarRocksMetadata:
    @pytest.mark.asyncio
    async def test_get_all_tables_uses_show_tables(self):
        captured = {}
        engine = FakeStarRocksEngine({})

        async def fake_query(db_name, sql, limit_num=0, parameters=None, **kwargs):
            captured["db_name"] = db_name
            captured["sql"] = sql
            captured["parameters"] = parameters
            return ResultSet(rows=[{"Tables_in_demo": "orders"}])

        engine.query = fake_query

        rs = await engine.get_all_tables("demo")

        assert rs.rows == [{"Tables_in_demo": "orders"}]
        assert captured["db_name"] == "demo"
        assert captured["sql"] == "SHOW TABLES FROM `demo`"
        assert captured["parameters"] is None


class TestStarRocksExecuteCheck:
    def setup_method(self):
        self.engine = StarRocksEngine(MockInstance())

    @pytest.mark.asyncio
    async def test_delete_without_where_rejected(self):
        review = await self.engine.execute_check("testdb", "DELETE FROM orders")
        assert review.error_count == 1
        assert "WHERE" in review.rows[0].errormessage

    @pytest.mark.asyncio
    async def test_delete_limit_rejected(self):
        review = await self.engine.execute_check(
            "testdb", "DELETE FROM orders WHERE id > 100 LIMIT 10"
        )
        assert review.error_count == 1
        assert "DELETE ... LIMIT" in review.rows[0].errormessage

    @pytest.mark.asyncio
    async def test_drop_table_warns(self):
        review = await self.engine.execute_check("testdb", "DROP TABLE old_orders")
        assert review.warning_count == 1
        assert "高风险" in review.rows[0].errormessage


class TestStarRocksCapabilities:
    @pytest.mark.asyncio
    async def test_regular_account_degrades_cluster_metrics(self):
        engine = FakeStarRocksEngine({
            "current_version": ResultSet(rows=[{"version": "3.3.0"}], column_list=["version"]),
            "show processlist": ResultSet(rows=[{"Id": 1, "Command": "Query"}], column_list=["Id", "Command"]),
            "show frontends": ResultSet(error="Access denied; require SYSTEM OPERATE"),
            "show proc '/backends'": ResultSet(error="Access denied; require SYSTEM OPERATE"),
            "show proc '/compute_nodes'": ResultSet(error="Access denied; require SYSTEM OPERATE"),
        })

        metrics = await engine.collect_metrics()

        assert metrics["health"]["up"] == 1
        assert metrics["queries"]["current"] == 1
        assert "缺少 SYSTEM OPERATE" in metrics["cluster"]["frontends"]["warning"]

    @pytest.mark.asyncio
    async def test_privileged_account_enables_cluster_capabilities(self):
        engine = FakeStarRocksEngine({
            "show grants": ResultSet(rows=[{"Grants": "GRANT cluster_admin TO USER admin"}]),
            "show processlist": ResultSet(rows=[{"Id": 1, "Command": "Query"}]),
            "show frontends": ResultSet(rows=[{"Name": "fe1"}]),
            "show proc '/backends'": ResultSet(rows=[{"BackendId": 1}]),
        })

        caps = await engine.probe_capabilities(force=True)

        assert caps.basic_rw is True
        assert caps.process_read is True
        assert caps.cluster_inspect is True
        assert caps.session_kill is True
        assert caps.variable_write is True
