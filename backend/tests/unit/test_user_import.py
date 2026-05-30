"""
用户导入单元测试。
"""

from unittest.mock import AsyncMock

import pytest

from app.services.user import UserService


class TestUserImportUserGroups:
    @pytest.mark.asyncio
    async def test_resolve_user_group_ids_auto_creates_missing_with_display_name(self):
        class EmptyResult:
            def all(self):
                return []

        class FakeDb:
            def __init__(self):
                self.created_groups = []

            async def execute(self, _stmt):
                return EmptyResult()

            def add(self, group):
                group.id = 100 + len(self.created_groups)
                self.created_groups.append(group)

            async def flush(self):
                return None

        db = FakeDb()

        group_ids, created_groups = await UserService._resolve_user_group_ids(
            db,
            "开发组;DBA组;开发组",
            auto_create_missing=True,
        )

        assert group_ids == [100, 101]
        assert created_groups == ["开发组", "DBA组"]
        assert [(group.name, group.name_cn) for group in db.created_groups] == [
            ("开发组", "开发组"),
            ("DBA组", "DBA组"),
        ]

    @pytest.mark.asyncio
    async def test_import_users_returns_auto_created_user_group_count(self, monkeypatch):
        rows = [
            {"normalized": {"username": "zhangsan"}, "raw": {"username": "zhangsan"}},
            {"normalized": {"username": "lisi"}, "raw": {"username": "lisi"}},
        ]
        upsert_results = iter([("created", 2), ("updated", 1)])

        async def fake_upsert(_db, _row, _default_password):
            return next(upsert_results)

        monkeypatch.setattr(
            UserService,
            "_parse_user_import_rows",
            staticmethod(lambda _content, _suffix: (["username"], rows)),
        )
        monkeypatch.setattr(
            UserService,
            "_upsert_imported_user",
            staticmethod(fake_upsert),
        )

        db = AsyncMock()
        result = await UserService.import_users(
            db=db,
            filename="users.csv",
            content=b"unused",
            default_password="Sagitta@2026A",
        )

        assert result["created"] == 1
        assert result["updated"] == 1
        assert result["auto_created_user_groups"] == 3
        assert result["failed"] == 0
        db.commit.assert_awaited_once()
