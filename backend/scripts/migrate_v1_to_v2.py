"""
数据迁移脚本：v1 权限体系 → v2 授权体系

Phase 2 迁移策略：
1. 超级管理员 → 分配 superadmin 角色
2. 根据用户权限码匹配内置角色（dba / dba_group / developer）
3. 权限码不完全匹配任何内置角色 → 创建自定义角色
4. user_resource_group → 为每个资源组创建默认用户组，将用户加入该组并关联资源组

用法：
    docker compose exec backend python -m scripts.migrate_v1_to_v2 [--dry-run]
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.role import (
    Role,
    UserGroup,
    group_resource_group,
    role_permission,
    user_group_member,
)
from app.models.user import Permission, Users, user_permission, user_resource_group

# ── 内置角色权限码映射 ──────────────────────────────────────────

SUPERADMIN_PERMS = {
    "menu_dashboard",
    "menu_sqlworkflow",
    "menu_query",
    "menu_ops",
    "sql_submit",
    "sql_review",
    "sql_execute",
    "sql_execute_for_resource_group",
    "query_submit",
    "query_applypriv",
    "query_review",
    "query_mgtpriv",
    "query_all_instances",
    "query_resource_group_instance",
    "process_view",
    "process_kill",
    "menu_monitor",
    "monitor_all_instances",
    "monitor_config_manage",
    "monitor_apply",
    "monitor_review",
    "monitor_alert_manage",
    "archive_apply",
    "archive_review",
    "audit_user",
    "menu_system",
    "menu_audit",
    "system_config_manage",
    "instance_manage",
    "resource_group_manage",
    "user_manage",
}

DBA_PERMS = {
    "menu_dashboard",
    "menu_sqlworkflow",
    "menu_query",
    "menu_ops",
    "sql_submit",
    "sql_review",
    "sql_execute",
    "sql_execute_for_resource_group",
    "query_submit",
    "query_applypriv",
    "query_review",
    "query_mgtpriv",
    "query_all_instances",
    "process_view",
    "process_kill",
    "menu_monitor",
    "monitor_all_instances",
    "monitor_config_manage",
    "monitor_apply",
    "monitor_review",
    "monitor_alert_manage",
    "archive_apply",
    "archive_review",
    "audit_user",
    "menu_audit",
    "instance_manage",
    "resource_group_manage",
}

DBA_GROUP_PERMS = {
    "menu_dashboard",
    "menu_sqlworkflow",
    "menu_query",
    "menu_ops",
    "sql_submit",
    "sql_review",
    "sql_execute",
    "sql_execute_for_resource_group",
    "query_submit",
    "query_applypriv",
    "query_review",
    "query_mgtpriv",
    "query_resource_group_instance",
    "process_view",
    "process_kill",
    "menu_monitor",
    "monitor_config_manage",
    "monitor_apply",
    "monitor_review",
    "archive_apply",
    "archive_review",
    "audit_user",
    "menu_audit",
    "instance_manage",
    "resource_group_manage",
}

DEVELOPER_PERMS = {
    "menu_dashboard",
    "menu_sqlworkflow",
    "menu_query",
    "sql_submit",
    "query_submit",
    "query_applypriv",
}


def match_role(user_perms: set[str]) -> str | None:
    if user_perms <= DEVELOPER_PERMS and user_perms >= DEVELOPER_PERMS:
        return "developer"
    if user_perms <= DBA_GROUP_PERMS:
        if user_perms >= DBA_GROUP_PERMS:
            return "dba_group"
        return "dba_group"
    if user_perms <= DBA_PERMS:
        return "dba"
    if user_perms <= SUPERADMIN_PERMS:
        return "superadmin"
    return None


def migrate(dry_run: bool = False) -> None:
    sync_url = (
        settings.DATABASE_URL_SYNC
        if hasattr(settings, "DATABASE_URL_SYNC")
        else str(settings.DATABASE_URL)
        .replace("+aiopg", "")
        .replace("+asyncpg", "")
        .replace("+aiomysql", "+pymysql")
    )
    engine = create_engine(sync_url, echo=False)

    with Session(engine) as session:
        print("=== v1 → v2 数据迁移开始 ===\n")

        # ── Step 0: 确保内置角色和权限已初始化 ──
        role_count = session.execute(select(func.count(Role.id))).scalar_one()
        if role_count == 0:
            print(
                "[Step 0] 内置角色未初始化，请先运行 /api/v1/system/init/ 或手动调用 init_builtin_roles"
            )
            return

        perm_rows = session.execute(select(Permission)).scalars().all()
        perm_by_code: dict[str, int] = {p.codename: p.id for p in perm_rows}
        print(f"[Step 0] 已有 {len(perm_by_code)} 个权限码, {role_count} 个角色\n")

        # ── Step 1: 迁移用户权限 → 角色分配 ──
        print("[Step 1] 迁移用户权限 → 角色分配")
        users = session.execute(select(Users)).scalars().all()

        role_by_name: dict[str, Role] = {}
        for r in session.execute(select(Role)).scalars().all():
            role_by_name[r.name] = r

        custom_role_counter = 0
        for user in users:
            if user.role_id is not None:
                print(f"  用户 {user.username}(ID={user.id}) 已有角色 ID={user.role_id}，跳过")
                continue

            # 获取用户直接权限
            if user.is_superuser:
                role_name = "superadmin"
                print(f"  用户 {user.username}(ID={user.id}) 是超级管理员 → 分配 superadmin")
            else:
                perm_rows_user = (
                    session.execute(
                        select(Permission.codename)
                        .join(user_permission, Permission.id == user_permission.c.permission_id)
                        .where(user_permission.c.user_id == user.id)
                    )
                    .scalars()
                    .all()
                )
                user_perms = set(perm_rows_user)

                if not user_perms:
                    print(f"  用户 {user.username}(ID={user.id}) 无权限 → 不分配角色")
                    continue

                role_name = match_role(user_perms)

                if role_name is None:
                    custom_role_counter += 1
                    role_name_custom = f"custom_role_{custom_role_counter}"
                    print(
                        f"  用户 {user.username}(ID={user.id}) 权限 {user_perms} 不匹配内置角色 → 创建自定义角色 {role_name_custom}"
                    )

                    if not dry_run:
                        role_obj = Role(
                            name=role_name_custom,
                            name_cn=f"自定义角色{custom_role_counter}",
                            description=f"从用户 {user.username} 的权限自动迁移",
                            is_system=False,
                            is_active=True,
                            tenant_id=1,
                        )
                        session.add(role_obj)
                        session.flush()

                        for code in user_perms:
                            if code in perm_by_code:
                                session.execute(
                                    role_permission.insert().values(
                                        role_id=role_obj.id,
                                        permission_id=perm_by_code[code],
                                    )
                                )
                        role_by_name[role_name_custom] = role_obj
                        user.role_id = role_obj.id
                    continue

                print(f"  用户 {user.username}(ID={user.id}) 权限匹配 → {role_name}")

            if not dry_run and role_name in role_by_name:
                user.role_id = role_by_name[role_name].id

        if not dry_run:
            session.flush()
        print()

        # ── Step 2: 迁移 user_resource_group → UserGroup ──
        print("[Step 2] 迁移 user_resource_group → UserGroup")
        rg_rows = session.execute(
            text("SELECT id, group_name, group_name_cn FROM resource_group")
        ).fetchall()

        for rg_id, group_name, group_name_cn in rg_rows:
            rg_label = group_name_cn or group_name

            existing_ug = session.execute(
                select(UserGroup).where(UserGroup.name == f"rg_{group_name}")
            ).scalar_one_or_none()

            if existing_ug:
                ug_id = existing_ug.id
                print(f"  资源组 '{rg_label}' 的用户组已存在 (ID={ug_id})，跳过创建")
            else:
                print(f"  为资源组 '{rg_label}' 创建默认用户组")
                if not dry_run:
                    ug = UserGroup(
                        name=f"rg_{group_name}",
                        name_cn=f"{rg_label}用户组",
                        description=f"自动迁移：资源组 {rg_label} 的成员",
                        is_active=True,
                        tenant_id=1,
                    )
                    session.add(ug)
                    session.flush()
                    ug_id = ug.id
                else:
                    ug_id = 0

            # 关联用户组 → 资源组
            if not dry_run and ug_id:
                existing_link = session.execute(
                    select(group_resource_group)
                    .where(group_resource_group.c.group_id == ug_id)
                    .where(group_resource_group.c.resource_group_id == rg_id)
                ).first()
                if not existing_link:
                    session.execute(
                        group_resource_group.insert().values(
                            group_id=ug_id, resource_group_id=rg_id
                        )
                    )

            # 获取资源组的直接用户
            user_ids = (
                session.execute(
                    select(user_resource_group.c.user_id).where(
                        user_resource_group.c.resource_group_id == rg_id
                    )
                )
                .scalars()
                .all()
            )

            if user_ids:
                print(f"    迁移 {len(user_ids)} 个用户到组 rg_{group_name}（资源组 {rg_label}）")
                if not dry_run and ug_id:
                    for uid in user_ids:
                        existing_member = session.execute(
                            select(user_group_member)
                            .where(user_group_member.c.group_id == ug_id)
                            .where(user_group_member.c.user_id == uid)
                        ).first()
                        if not existing_member:
                            session.execute(
                                user_group_member.insert().values(group_id=ug_id, user_id=uid)
                            )

        if not dry_run:
            session.flush()
        print()

        # ── Step 3: 审计总结 ──
        print("[Step 3] 迁移总结")
        total_users = session.execute(select(func.count(Users.id))).scalar_one()
        users_with_role = session.execute(
            select(func.count(Users.id)).where(Users.role_id.isnot(None))
        ).scalar_one()
        total_groups = session.execute(select(func.count(UserGroup.id))).scalar_one()
        total_links = session.execute(
            select(func.count(group_resource_group.c.group_id))
        ).scalar_one()
        total_members = session.execute(
            select(func.count(user_group_member.c.group_id))
        ).scalar_one()

        print(f"  总用户数: {total_users}")
        print(f"  已分配角色: {users_with_role}")
        print(f"  用户组总数: {total_groups}")
        print(f"  用户组→资源组关联: {total_links}")
        print(f"  用户组→成员关联: {total_members}")

        if dry_run:
            print("\n=== DRY RUN — 未做任何修改 ===")
            session.rollback()
        else:
            session.commit()
            print("\n=== 迁移完成，已提交 ===")
            print("注意：旧表 user_permission 和 user_resource_group 仍保留，Phase 4 清理")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sagitta Control v1→v2 权限体系迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅打印迁移计划，不修改数据")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
