# SagittaDB 授权体系设计方案（v1 — 现状）

> ⚠️ **本方案描述的是当前系统的权限体系现状。** 下一版本重设计方案请见 [sagittadba_auth_redesign_v2.md](sagittadba_auth_redesign_v2.md)，包含角色系统（Role）、用户组（UserGroup）、资源组职责拆分、四级授权粒度、直属上级审批节点、短信验证码等全面升级。

---

## 一、现状分析

### 整体架构：三层叠加模型

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: 身份层                                      │
│  超级管理员(is_superuser) ↔ 普通用户                  │
├─────────────────────────────────────────────────────┤
│  Layer 2: 功能权限层（Permission codename）            │
│  27 个权限码，直接绑定到用户（user_permission 关联表） │
├─────────────────────────────────────────────────────┤
│  Layer 3: 资源隔离层（ResourceGroup）                 │
│  用户 ↔ 资源组 ↔ 实例（三方多对多）                   │
└─────────────────────────────────────────────────────┘
```

**Layer 1：超级管理员**

- `is_superuser = true` → 绕过所有权限检查，直接放行
- 在 `require_perm()` 和查询三层校验（`check_query_priv`）中都有 superuser 短路逻辑

---

### 27 个功能权限码

| 模块 | 权限码 | 说明 |
|------|--------|------|
| 菜单 | `menu_dashboard` `menu_sqlworkflow` `menu_observability` | 控制菜单可见性 |
| SQL 工单 | `sql_submit` `sql_review` `sql_execute` `sql_execute_for_resource_group` | 提交/审核/执行 |
| 在线查询 | `query_submit` `query_applypriv` `query_review` `query_mgtpriv` `query_all_instances` `query_resource_group_instance` | 查询及权限申请审批 |
| 观测中心 | `observability_instance_all` `observability_session_view` `observability_session_kill` `observability_sql_view` `observability_sql_analyze` `observability_collect_manage` `observability_alert_manage` | 实例观测、会话洞察、SQL 洞察、采集配置与告警 |
| 归档 | `archive_apply` `archive_review` | 数据归档申请审批 |
| 系统管理 | `system_config_manage` `instance_manage` `resource_group_manage` `user_manage` `audit_user` | 系统级管理 |

每个 API endpoint 都通过 `Depends(require_perm("xxx"))` 做强制校验，未授权直接 403。

---

### 在线查询资源组隔离（三层递进校验）

```
L0: 数据库启停控制（is_active）
    is_active=False 的数据库：
    - 普通用户：API 列表过滤 + 查询返回 403
    - 管理员：可见，下拉框标灰显示"已禁用"
    ↓ is_active=True 才继续
L1: is_superuser 或 query_all_instances → 直接放行
    ↓ 否则
L2: 实例是否在用户的资源组内 → 不在则拒绝
    ↓ 通过
L3: 库/表级权限记录（QueryPrivilege）
    - priv_type=1 → DATABASE 级（库级授权）
    - priv_type=2 → TABLE 级（表级授权）
    - 有效期 valid_date 控制
```

SQL 工单没有 L3，只要有 `sql_submit` 权限 + 实例在资源组内就能提交。

---

### 现状已知缺陷

| # | 问题 | 具体表现 |
|---|------|----------|
| 1 | 无用户组 | 权限只能逐人配置，无法批量管理 |
| 2 | 无角色 | 27个权限码直接绑 User，无法复用 |
| 3 | 无审批链结构 | `audit_auth_groups` 是逗号字符串，无法支持组长优先 |
| 4 | 查询权限只到用户 | `QueryPrivilege.user_id` 无法授权给组 |
| 5 | ResourceGroup 只绑用户 | 无法把整组人加入资源组 |
| 6 | 租户隔离未强制 | `tenant_id` 字段预留但查询中未强制过滤，实际等于单租户 |

---

## 二、新授权体系重设计方案

### 四层模型总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        授权主体（Who）                            │
│                                                                  │
│   User ─────┬──── UserGroup（有 leader）                         │
│             │         └── parent UserGroup（支持层级）            │
└─────────────┼────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│                       功能权限（What Can Do）                     │
│                                                                  │
│   Role ──── role_permission ──── Permission(codename)            │
│    │                                                             │
│    ├── user_role ──── User（直接赋角色）                          │
│    └── user_group_role ──── UserGroup（组级赋角色，成员继承）      │
└──────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      资源访问范围（Which Resource）               │
│                                                                  │
│   ResourceGroup ◄──── user_resource_group ──── User              │
│        │        ◄──── group_resource_group ──── UserGroup        │
│        └──── instance_resource_group ──── Instance               │
└──────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    数据级权限（Which Data）                        │
│                                                                  │
│   QueryPrivilege:                                                │
│     subject = User  (user_id, group_id=null)                     │
│     OR                                                           │
│     subject = UserGroup (user_id=null, group_id=FK)              │
│     scope  = Instance + DB + Table + valid_date + limit_num      │
└──────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      审批链（Approval Flow）                      │
│                                                                  │
│   Step 0（自动注入）: 提交人所在用户组的 leader                   │
│   Step 1+（可配置）:                                             │
│     - 指定用户                                                   │
│     - 指定用户组（组内任一成员可审批）                            │
│     - 拥有某权限的用户（如 sql_review）                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、数据模型设计

### 1. UserGroup（用户组）

```python
class UserGroup(BaseModel):
    __tablename__ = "user_group"

    id          : int
    name        : str        # 唯一英文标识，如 "dba-team"
    name_cn     : str        # 显示名，如 "数据库团队"
    description : str
    leader_id   : int | None  # FK → sql_users.id，组长（可空）
    parent_id   : int | None  # FK → user_group.id，父组（支持层级）
    is_active   : bool
```

```sql
-- 关联表
user_group_member (user_id, group_id)   -- 用户归属组
```

### 2. Role（角色）

```python
class Role(BaseModel):
    __tablename__ = "role"

    id          : int
    name        : str    # 唯一，如 "dba", "developer", "auditor"
    name_cn     : str    # "DBA", "开发工程师", "审计员"
    description : str
    is_system   : bool   # True = 内置角色不可删除
```

```sql
-- 关联表
role_permission  (role_id, permission_codename)  -- 角色包含哪些权限
user_role        (user_id, role_id)              -- 用户直接赋角色
user_group_role  (group_id, role_id)             -- 用户组赋角色
```

### 3. ResourceGroup 扩展

```sql
-- 新增关联表（原 user_resource_group 保留）
group_resource_group (group_id, resource_group_id)
```

### 4. QueryPrivilege 扩展

```python
# 保留现有字段，新增：
user_group_id : int | None  # FK → user_group.id
# CHECK: user_id IS NOT NULL OR user_group_id IS NOT NULL
```

### 5. WorkflowApprovalStep（替代字符串审批链）

```python
class WorkflowApprovalStep(BaseModel):
    __tablename__ = "workflow_approval_step"

    id            : int
    workflow_id   : int    # FK → sql_workflow.id 或 query_privilege_apply.id
    workflow_type : int    # WorkflowType 枚举

    step_order    : int    # 0 = 组长自动注入，1,2,3... = 配置审批节点

    # 审批人类型（四选一）
    approver_type      : str        # "group_leader" | "user" | "user_group" | "permission"
    approver_user_id   : int | None
    approver_group_id  : int | None
    approver_perm      : str | None

    # 审批结果
    status      : int           # AuditStatus 枚举
    auditor_id  : int | None
    audited_at  : datetime | None
    remark      : str
```

---

## 四、权限解析逻辑

### get_user_effective_permissions(user_id)

```sql
-- 步骤 1：直接角色权限
SELECT permission_codename FROM role_permission
JOIN user_role USING(role_id)
WHERE user_id = :user_id

UNION

-- 步骤 2：通过用户组继承的角色权限
SELECT permission_codename FROM role_permission
JOIN user_group_role USING(role_id)
JOIN user_group_member USING(group_id)
WHERE user_id = :user_id
```

`is_superuser = true` 直接绕过，不走以上查询。

### get_user_accessible_instances(user_id)

```
路径 1（直接）:
  User → user_resource_group → ResourceGroup → instance_resource_group → Instance

路径 2（通过用户组）:
  User → user_group_member → UserGroup → group_resource_group → ResourceGroup → Instance

合并取并集
```

### 审批链自动注入 auto_build_approval_chain(submitter_id, resource_group_id)

```python
steps = []

# Step 0：自动注入组长审批
group = get_user_primary_group(submitter_id)
if group and group.leader_id and group.leader_id != submitter_id:
    steps.append(Step(order=0, type="group_leader", group_id=group.id))

# Step 1+：读取资源组/工单类型绑定的配置审批节点
configured = get_approval_flow(resource_group_id, workflow_type)
for i, node in enumerate(configured, start=1):
    steps.append(Step(order=i, **node))

return steps
```

---

## 五、内置角色建议（is_system=True）

| 角色名 | 典型权限 | 适用人员 |
|--------|----------|----------|
| `superadmin` | 全部权限 | 系统管理员 |
| `dba` | `instance_manage` + `sql_review` + `sql_execute` + `query_all_instances` + `observability_instance_all` | DBA |
| `developer` | `sql_submit` + `query_submit` + `query_applypriv` + `archive_apply` | 开发工程师 |
| `auditor` | `sql_review` + `query_review` + `audit_user` | 审计/安全 |
| `viewer` | `menu_dashboard` + `query_submit`（需申请后） | 只读用户 |

---

## 六、迁移策略（不破坏现有数据）

### Phase 1：新建表，不动旧表

- 建 `user_group` / `role` / `user_group_member` / `role_permission` / `user_role` / `user_group_role`
- 建 `workflow_approval_step`
- `query_privilege` 新增 `user_group_id` 列（nullable，旧数据为 null）
- 新增 `group_resource_group` 关联表

### Phase 2：数据迁移

- 现有 `user_permission` → 自动生成对应 `Role` + `user_role` 记录
- `audit_auth_groups` 字符串 → 解析为 `WorkflowApprovalStep` 记录

### Phase 3：切换逻辑

- `require_perm()` 改为读 Role 继承链
- `check_query_priv()` 加入 UserGroup 路径
- 提交工单时调用 `auto_build_approval_chain()`
- 废弃 `audit_auth_groups` 字符串字段

---

## 七、各概念职责边界

| 概念 | 职责 | 类比 |
|------|------|------|
| **用户组** | 组织单位，决定审批链（谁审谁） | 部门/团队 |
| **角色** | 功能权限集合，决定能做什么操作 | 岗位职责 |
| **资源组** | 实例访问范围，决定能操作哪些库 | 数据域 |
| **QueryPrivilege** | 细粒度数据访问，决定能查哪张表 | 表级 ACL |
