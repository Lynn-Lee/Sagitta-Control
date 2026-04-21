"""
Oracle 引擎驱动模式测试。
"""

import app.engines.oracle as oracle_module
from app.engines.oracle import OracleEngine


class MockOracleInstance:
    host = "localhost"
    port = 1521
    user = ""
    password = ""
    db_name = "FREEPDB1"
    show_db_name_regex = ""


def _reset_oracle_client_state():
    oracle_module._ORACLE_CLIENT_INIT_ATTEMPTED = False
    oracle_module._ORACLE_CLIENT_INIT_ERROR = None


class TestOracleDriverMode:
    def test_connect_initializes_thick_mode_when_requested(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "thick")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        calls: list[tuple[str, dict]] = []

        def fake_init_oracle_client(**kwargs):
            calls.append(("init", kwargs))

        def fake_connect(**kwargs):
            calls.append(("connect", kwargs))
            return object()

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)
        monkeypatch.setattr(oracle_module.oracledb, "connect", fake_connect)

        engine = OracleEngine(instance=MockOracleInstance())
        conn = engine._connect_sync()

        assert conn is not None
        assert calls[0] == ("init", {})
        assert calls[1][0] == "connect"

    def test_auto_mode_falls_back_to_thin_when_thick_init_fails(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "auto")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        calls: list[str] = []

        def fake_init_oracle_client(**kwargs):
            calls.append("init")
            raise RuntimeError("DPI-1047: missing client")

        def fake_connect(**kwargs):
            calls.append("connect")
            return object()

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)
        monkeypatch.setattr(oracle_module.oracledb, "connect", fake_connect)

        engine = OracleEngine(instance=MockOracleInstance())
        conn = engine._connect_sync()

        assert conn is not None
        assert calls == ["init", "connect"]

    def test_thick_mode_raises_when_client_init_fails(self, monkeypatch):
        _reset_oracle_client_state()
        monkeypatch.setattr("app.engines.oracle.decrypt_field", lambda value: value)
        monkeypatch.setattr(oracle_module.settings, "ORACLE_DRIVER_MODE", "thick")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_LIB_DIR", "")
        monkeypatch.setattr(oracle_module.settings, "ORACLE_CLIENT_CONFIG_DIR", "")

        def fake_init_oracle_client(**kwargs):
            raise RuntimeError("DPI-1047: missing client")

        monkeypatch.setattr(oracle_module.oracledb, "init_oracle_client", fake_init_oracle_client)

        engine = OracleEngine(instance=MockOracleInstance())

        try:
            engine._connect_sync()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected RuntimeError")

        assert "ORACLE_DRIVER_MODE=thick" in message
        assert "DPI-1047" in message
