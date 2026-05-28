"""
系统配置服务单元测试。
验证配置读写、加密字段处理、批量更新逻辑。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.system_config import CONFIG_DEFINITIONS, CONFIG_ORDER, SystemConfigService


class TestConfigDefinitions:
    """验证 CONFIG_DEFINITIONS 结构完整性。"""

    def test_all_configs_have_four_fields(self):
        for key, val in CONFIG_DEFINITIONS.items():
            assert len(val) == 4, f"配置 {key} 结构不正确: {val}"

    def test_sensitive_fields_marked(self):
        sensitive_keys = {k for k, v in CONFIG_DEFINITIONS.items() if v[2]}
        # 密码/密钥字段必须被标记为敏感
        for k in sensitive_keys:
            assert any(
                s in k for s in ["password", "secret", "key", "token", "webhook"]
            ), f"敏感字段命名不符合规范: {k}"

    def test_ldap_group_config_exists(self):
        ldap_keys = [k for k, v in CONFIG_DEFINITIONS.items() if v[1] == "ldap"]
        assert "ldap_server_uri" in ldap_keys
        assert "ldap_bind_dn" in ldap_keys
        assert "ldap_bind_password" in ldap_keys
        assert "ldap_enabled" in ldap_keys

    def test_branding_config_exists(self):
        assert CONFIG_DEFINITIONS["platform_name"][1] == "basic"
        assert CONFIG_DEFINITIONS["platform_logo_url"][1] == "basic"

    def test_ai_group_config_exists(self):
        ai_keys = [k for k, v in CONFIG_DEFINITIONS.items() if v[1] == "ai"]
        assert "ai_enabled" in ai_keys
        assert "ai_provider" in ai_keys
        assert "ai_base_url" in ai_keys
        assert "ai_api_key" in ai_keys
        assert CONFIG_ORDER["ai_enabled"] > CONFIG_ORDER["ai_model"]

    def test_no_duplicate_keys(self):
        keys = list(CONFIG_DEFINITIONS.keys())
        assert len(keys) == len(set(keys)), "存在重复的配置 key"

    def test_sso_enable_switches_render_after_main_fields(self):
        assert CONFIG_ORDER["ldap_enabled"] > CONFIG_ORDER["ldap_attr_title"]
        assert CONFIG_ORDER["cas_enabled"] > CONFIG_ORDER["cas_username_attribute"]
        assert CONFIG_ORDER["oidc_enabled"] > CONFIG_ORDER["oidc_display_name_claim"]
        assert CONFIG_ORDER["sms_enabled"] > CONFIG_ORDER["sms_endpoint"]


class TestGetValue:
    """测试 SystemConfigService.get_value 读取逻辑。"""

    @pytest.mark.asyncio
    async def test_returns_default_when_not_in_db(self):
        """DB 中无该 key 时，应返回 CONFIG_DEFINITIONS 中的默认值。"""
        mock_db = AsyncMock()
        # scalar_one_or_none 返回 None（DB 中无此 key）
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        val = await SystemConfigService.get_value(mock_db, "ldap_user_filter")
        # 应该返回默认值
        assert val == CONFIG_DEFINITIONS["ldap_user_filter"][3]

    @pytest.mark.asyncio
    async def test_returns_plain_value(self):
        """非加密字段直接返回 config_value。"""
        mock_db = AsyncMock()
        mock_cfg = MagicMock()
        mock_cfg.config_value = "ldap://myserver:389"
        mock_cfg.is_encrypted = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cfg
        mock_db.execute = AsyncMock(return_value=mock_result)

        val = await SystemConfigService.get_value(mock_db, "ldap_server_uri")
        assert val == "ldap://myserver:389"

    @pytest.mark.asyncio
    async def test_returns_decrypted_value_for_sensitive(self):
        """加密字段应自动解密后返回。"""
        from app.core.security import encrypt_field

        mock_db = AsyncMock()
        encrypted = encrypt_field("my_secret_password")
        mock_cfg = MagicMock()
        mock_cfg.config_value = encrypted
        mock_cfg.is_encrypted = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cfg
        mock_db.execute = AsyncMock(return_value=mock_result)

        val = await SystemConfigService.get_value(mock_db, "ldap_bind_password")
        assert val == "my_secret_password"

    @pytest.mark.asyncio
    async def test_unknown_key_returns_empty_string(self):
        """未知 key 应返回空字符串（不抛异常）。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        val = await SystemConfigService.get_value(mock_db, "non_existent_key_xyz")
        assert val == ""


class TestPublicAuthMethods:
    """测试登录页公开认证方式开关。"""

    @pytest.mark.asyncio
    async def test_returns_only_boolean_auth_method_flags(self):
        mock_db = AsyncMock()
        values = {
            "ldap_enabled": "true",
            "cas_enabled": "false",
            "ding_login_enabled": "true",
            "feishu_login_enabled": "",
            "wecom_login_enabled": "TRUE",
            "sms_enabled": "true",
            "oidc_enabled": "false",
        }

        async def fake_get_value(_db, key):
            return values[key]

        with (
            patch.object(SystemConfigService, "_ensure_defaults", new=AsyncMock()),
            patch.object(SystemConfigService, "get_value", side_effect=fake_get_value),
        ):
            methods = await SystemConfigService.get_public_auth_methods(mock_db)

        assert methods == {
            "ldap": True,
            "cas": False,
            "dingtalk": True,
            "feishu": False,
            "wecom": True,
            "sms": True,
            "oidc": False,
        }


class TestEnsureDefaults:
    """测试默认配置初始化与元数据刷新。"""

    @pytest.mark.asyncio
    async def test_refreshes_existing_metadata_without_overwriting_value(self):
        mock_db = AsyncMock()
        existing = MagicMock()
        existing.description = "Anthropic API Key"
        existing.group = "old_group"
        existing.config_value = "encrypted_saved_key"

        keys = iter(CONFIG_DEFINITIONS.keys())

        async def fake_execute(_stmt):
            key = next(keys)
            result = MagicMock()
            result.scalar_one_or_none.return_value = existing if key == "ai_api_key" else None
            return result

        mock_db.execute = AsyncMock(side_effect=fake_execute)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        await SystemConfigService._ensure_defaults(mock_db)

        assert existing.description == CONFIG_DEFINITIONS["ai_api_key"][0]
        assert existing.group == "ai"
        assert existing.config_value == "encrypted_saved_key"


class TestConnectivityChecks:
    """测试系统配置连通性检查的基础配置校验。"""

    @pytest.mark.asyncio
    async def test_cas_requires_server_url(self):
        mock_db = AsyncMock()
        with patch.object(SystemConfigService, "get_value", new=AsyncMock(return_value="")):
            result = await SystemConfigService.test_cas(mock_db)

        assert result == {"success": False, "message": "CAS 服务器地址未配置"}

    @pytest.mark.asyncio
    async def test_oidc_requires_issuer_or_manual_endpoints(self):
        mock_db = AsyncMock()
        values = {
            "oidc_issuer_url": "",
            "oidc_authorization_endpoint": "",
            "oidc_token_endpoint": "",
        }

        async def fake_get_value(_db, key):
            return values[key]

        with patch.object(SystemConfigService, "get_value", side_effect=fake_get_value):
            result = await SystemConfigService.test_oidc(mock_db)

        assert result == {
            "success": False,
            "message": "OIDC Issuer 地址未配置；如不使用自动发现，请填写授权端点和 Token 端点",
        }


class TestUpdateBatch:
    """测试 SystemConfigService.update_batch 批量写入逻辑。"""

    @pytest.mark.asyncio
    async def test_skips_unknown_keys(self):
        """未在 CONFIG_DEFINITIONS 中的 key 应被跳过。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count, _ = await SystemConfigService.update_batch(
            mock_db, {"unknown_key_abc": "value", "another_bad_key": "v2"}
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_skips_empty_sensitive_field(self):
        """空密码字段不应覆盖原有值（防止意外清空密码）。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count, _ = await SystemConfigService.update_batch(
            mock_db, {"ldap_bind_password": ""}
        )
        assert count == 0  # 空敏感字段被跳过

    @pytest.mark.asyncio
    async def test_skips_masked_sensitive_field(self):
        """掩码值 '******' 不应覆盖原有密码。"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count, _ = await SystemConfigService.update_batch(
            mock_db, {"ldap_bind_password": "******"}
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_updates_existing_record(self):
        """已存在的配置项应被更新（UPDATE）。"""
        from app.models.system import SystemConfig

        mock_db = AsyncMock()
        existing = MagicMock(spec=SystemConfig)
        existing.config_value = "old_value"
        existing.is_encrypted = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        count, summary = await SystemConfigService.update_batch(
            mock_db, {"ldap_server_uri": "ldap://newserver:389"}
        )
        assert count == 1
        assert existing.config_value == "ldap://newserver:389"

    @pytest.mark.asyncio
    async def test_creates_new_record(self):
        """不存在的配置项应被创建（INSERT）。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count, _ = await SystemConfigService.update_batch(
            mock_db, {"ldap_server_uri": "ldap://test:389"}
        )
        assert count == 1
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_encrypts_sensitive_field(self):
        """有值的敏感字段应加密存储，is_encrypted 设为 True。"""
        from app.core.security import decrypt_field
        from app.models.system import SystemConfig

        mock_db = AsyncMock()
        existing = MagicMock(spec=SystemConfig)
        existing.is_encrypted = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        await SystemConfigService.update_batch(
            mock_db, {"ldap_bind_password": "secret123"}
        )
        # 应该是加密后的值（不等于原始值）
        assert existing.config_value != "secret123"
        assert existing.is_encrypted is True
        # 解密后应等于原始值
        assert decrypt_field(existing.config_value) == "secret123"

    @pytest.mark.asyncio
    async def test_returns_change_summary(self):
        """应返回变更摘要列表，敏感字段不记录具体值。"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        count, summary = await SystemConfigService.update_batch(
            mock_db,
            {"ldap_server_uri": "ldap://test:389", "ldap_bind_password": "pass123"},
        )
        assert count == 2
        # 敏感字段摘要不包含密码值
        sensitive_entry = next((s for s in summary if "密码" in s or "password" in s.lower()), "")
        assert "pass123" not in sensitive_entry

    @pytest.mark.asyncio
    async def test_rejects_unsafe_logo_url(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.commit = AsyncMock()

        with pytest.raises(ValueError, match="Logo"):
            await SystemConfigService.update_batch(
                mock_db, {"platform_logo_url": "javascript:alert(1)"}
            )

    @pytest.mark.asyncio
    async def test_rejects_overlong_platform_name(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.commit = AsyncMock()

        with pytest.raises(ValueError, match="平台名称"):
            await SystemConfigService.update_batch(mock_db, {"platform_name": "x" * 81})
