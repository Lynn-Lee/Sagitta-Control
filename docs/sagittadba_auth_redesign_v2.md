# SagittaDB 授权体系重设计方案 v2

> **版本：** v1.0 · 2026-04-12
> **状态：** v2-lite 已落地并进入本地验收阶段（优先交付可解释、可测试、可落地版本）
> **前置文档：** [sagittadb_auth_design.md](sagittadb_auth_design.md)（v1 现状分析）

---

## 一、核心架构：五层模型

```
┌─────────────────────────────────────────────────────────────────┐
│  L0  数据库启停门控                InstanceDatabase.is_active     │
│      禁用库对非超管不可见/不可查                                   │
├─────────────────────────────────────────────────────────────────┤
│  L1  身份层                        User.is_superuser             │
│      超管绕过一切检查                                             │
├─────────────────────────────────────────────────────────────────┤
│  L2  功能权限层                     Role → Permission             │
│      用户绑定 1 个角色，角色是权限码的集合                         │
│      管理员可对内置角色微调权限码和菜单                            │
├─────────────────────────────────────────────────────────────────┤
│  L3  资源访问层                     UserGroup → ResourceGroup      │
│      用户组 → 资源组 ↔ 实例（资源组只包含实例，不含用户）          │
│      用户继承所属用户组的资源组访问权                              │
├─────────────────────────────────────────────────────────────────┤
│  L4  数据级权限层                   QueryPrivilege                │
│      首发仅支持：用户主体 + 库/表两级粒度                          │
│      实例范围由资源组链路承担，数据授权只补充“能查哪些库/表”        │
├─────────────────────────────────────────────────────────────────┤
│  L5  审批流层                      ApprovalFlow + 自动节点        │
│      首发节点：直属上级 / 指定用户 / 任意审批员                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、四个内置角色

| Role name | 中文名 | `is_system` | 关键权限差异 | 典型用户 |
|---|---|---|---|---|
| `superadmin` | 超级管理员 | ✅ | `is_superuser=True`，绕过一切检查 | 平台管理员 |
| `dba` | 全局 DBA | ✅ | 包含 `query_all_instances` + `monitor_all_instances`，可见所有实例 | 基础设施 DBA |
| `dba_group` | 资源组 DBA | ✅ | **不含** `query_all_instances` + `monitor_all_instances`，实例范围限于资源组 | 业务 DBA、外包 DBA |
| `developer` | 开发工程师 | ✅ | `sql_submit` + `query_submit` + `query_applypriv`，不默认拥有监控/运维入口 | 研发工程师 |

### dba 与 dba_group 共有的核心权限码

```
sql_submit, sql_review, sql_execute, sql_execute_for_resource_group,
process_view, process_kill, instance_manage,
query_submit, query_applypriv, query_review, query_mgtpriv,
query_resource_group_instance,
monitor_config_manage, monitor_apply, monitor_review,
archive_apply, audit_user
```

### dba 独有而 dba_group 没有的

```
query_all_instances      # 可查询所有实例（不受资源组限制）
monitor_all_instances    # 可监控所有实例
```

管理员可在角色详情页增删权限码和菜单可见性，但不能删除或重命名 `is_system=True` 的内置角色。

### 菜单可见性控制

菜单实现以权限码为准，不再维护“角色 -> 菜单”的第二套真相：
`menu_dashboard` / `menu_sqlworkflow` / `menu_query` / `menu_ops` / `menu_monitor` / `menu_system` / `menu_audit`

| 菜单 | superadmin | dba | dba_group | developer |
|---|---|---|---|---|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| SQL 工单 | ✅ | ✅ | ✅ | ✅(仅提交) |
| 在线查询 | ✅ | ✅(全部实例) | ✅(所在组实例) | ✅(授权后) |
| 运维中心 | ✅ | ✅ | ✅ | ❌ |
| 可观测中心 | ✅ | ✅ | ✅(所在组) | ❌ |
| 系统管理 | ✅ | ❌ | ❌ | ❌ |

---

## 三、数据模型

### 3.1 Users 表变更

| 操作 | 字段 | 类型 | 说明 |
|---|---|---|---|
| **新增** | `role_id` | Integer FK→`role.id` nullable | 用户角色（单角色，null=未分配） |
| **新增** | `manager_id` | Integer FK→`sql_users.id` nullable | 直属上级，审批流"直属上级"节点自动解析 |
| **新增** | `employee_id` | String(50) `""` | 工号，LDAP/OAuth 同步填充 |
| **新增** | `department` | String(100) `""` | 部门，LDAP 同步填充 |
| **新增** | `title` | String(100) `""` | 职位/岗位，LDAP 同步填充 |
| 保留 | `is_superuser` | Boolean | 仅 `superadmin` 角色用户为 True |

### 3.2 新增 Role 模型

```python
class Role(BaseModel):
    __tablename__ = "role"
    id: int                       # PK
    name: str(50) unique           # "superadmin" / "dba" / "dba_group" / "developer"
    name_cn: str(100)             # "超级管理员" / "全局 DBA" / "资源组 DBA" / "开发工程师"
    description: str(500) = ""
    is_system: bool = False        # 内置角色不可删除
    is_active: bool = True         # 停用后新用户不可分配
    tenant_id: int = 1
    # relationships
    permissions: M2M → Permission via role_permission
```

### 3.3 新增 UserGroup 模型

```python
class UserGroup(BaseModel):
    __tablename__ = "user_group"
    id: int                       # PK
    name: str(100) unique          # "dba-team" / "payment-dev"
    name_cn: str(100)             # "DBA 组" / "支付研发组"
    description: str(500) = ""
    leader_id: int nullable FK→sql_users.id     # 组长
    parent_id: int nullable FK→user_group.id      # 父组（支持树形）
    is_active: bool = True
    tenant_id: int = 1
    # relationships
    members: M2M → Users via user_group_member
    resource_groups: M2M → ResourceGroup via group_resource_group
```

### 3.4 新增关联表

```python
# 角色-权限码关联
role_permission = Table(
    "role_permission",
    Column("role_id",       FK→role.id),
    Column("permission_id", FK→permission.id),
)

# 用户组成员
user_group_member = Table(
    "user_group_member",
    Column("user_id",  FK→sql_users.id),
    Column("group_id", FK→user_group.id),
)

# 用户组-资源组关联（用户组通过资源组获得实例访问权）
group_resource_group = Table(
    "group_resource_group",
    Column("group_id",           FK→user_group.id),
    Column("resource_group_id",  FK→resource_group.id),
)
```

### 3.5 ResourceGroup 变更

| 操作 | 说明 |
|---|---|
| **移除** | 删除 `user_resource_group` 关联表 |
| **保留** | `instance_resource_group`（实例仍属于资源组） |
| **新增** | `group_resource_group`（用户组可关联资源组） |

用户通过 **用户 → 用户组(*) → 资源组 → 实例** 链路获得实例访问权。

### 3.6 QueryPrivilege 扩展（v2-lite 首发）

| 操作 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 保留兼容 | `user_group_id` | Integer FK→`user_group.id` nullable | 二期预留，首发不走主流程 |
| 收敛 | `scope_type` | Enum | 首发仅 `database` / `table` |
| 保留兼容 | `resource_group_id` | Integer FK→`resource_group.id` nullable | 兼容旧迁移字段，首发不作为授权粒度 |
| 首发约束 | — | 规则 | 首发仅支持用户主体授权 |

**scope_type 与授权范围对应：**

| scope_type | 授权范围 | 必填字段 |
|---|---|---|
| `database` | 单个实例的单个库 | `instance_id` + `db_name` |
| `table` | 单个库的单个表 | `instance_id` + `db_name` + `table_name` |

### 3.7 ApprovalFlowNode 扩展

首发支持的 `approver_type`：

| approver_type | 说明 | 运行时解析 |
|---|---|---|
| `manager` | 直属上级 | `applicant.manager_id` → 找到审批人 |
| `users` | 指定用户 | `approver_ids` 中的用户 ID 列表 |
| `any_reviewer` | 任意拥有审批权限的人 | 不指定具体人 |

二期预留：`user_group` / `role`

---

## 四、权限解析逻辑

### 4.1 功能权限解析

```python
def get_user_permissions(user):
    if user.is_superuser:
        return ALL_PERMISSIONS
    
    role = user.role
    if not role:
        return set()  # 无角色 = 无权限
    
    # 权限码从 role_permission 关联表读取
    return {p.codename for p in role.permissions}
```

### 4.2 资源访问范围解析

```python
def get_user_accessible_instances(user):
    if user.is_superuser or "query_all_instances" in user.permissions:
        return ALL_INSTANCES
    
    # 用户 → 用户组 → 资源组 → 实例
    group_ids = [ug.id for ug in user.user_groups]
    rg_ids = select group_resource_group where group_id in group_ids
    instance_ids = select instance_resource_group where resource_group_id in rg_ids
    
    return instances_by_ids(instance_ids)
```

### 4.3 数据级权限解析优先级

```
首发授权范围优先级：table > database
首发授权主体：仅用户直接授权
```

用户查询时，系统先检查资源组实例可见性，再检查用户自己的 QueryPrivilege 记录，按 `table > database` 优先级判定。

---

## 五、认证方式总表

| 方式 | 状态 | 说明 |
|---|---|---|
| 账号密码 | ✅ 已有 | bcrypt + SHA-256 双重哈希；默认/弱/过期密码强制改密 |
| TOTP 两步验证 | ✅ 已有 | Google Authenticator 兼容 |
| LDAP 认证 | ✅ 已有 | 三步验证（bind→搜索→re-bind），自动 provision |
| 钉钉扫码 OAuth | ✅ 已有 | DingTalk New API v2，scope=openid |
| 飞书扫码 OAuth | ✅ 已有 | Feishu OIDC |
| 企微扫码 OAuth | ✅ 已有 | WeCom qrConnect |
| CAS 通用 SSO | ✅ 已有 | Keycloak / Okta / Azure AD，可配3个端点 |
| **短信验证码** | 🆕 新增 | 对接阿里云/腾讯云 SMS |

### 本地账号密码安全策略

- 密码复杂度：至少 8 位，必须包含数字、大写字母、小写字母和特殊字符。
- 登录校验：账号密码验证通过后继续检查默认密码、弱密码和密码过期状态；命中任一规则时不签发正式 access/refresh token，仅返回短效 `password_change` token。
- 强制改密：用户通过 `/auth/password/change-required/` 设置合规新密码，成功后必须使用新密码重新登录。
- 周期管理：`sql_users.password_changed_at` 记录最近一次改密时间，密码每 30 天必须修改一次，到期前 7 天通过 `/auth/me/` 返回提醒字段供前端展示。
- 用户导入：批量导入默认密码示例为 `Sagitta@2026A`，与创建用户、个人改密和强制改密共用同一套复杂度规则。

### 短信验证码新增配置项（SystemConfig `sms` 组）

| 配置键 | 说明 |
|---|---|
| `sms_enabled` | 是否启用短信登录 |
| `sms_provider` | `aliyun` / `tencent` |
| `sms_access_key` | SMS 服务 AccessKey（加密存储） |
| `sms_access_secret` | SMS 服务 AccessSecret（加密存储） |
| `sms_sign_name` | 短信签名 |
| `sms_template_code` | 验证码模板 ID |
| `sms_code_expire_minutes` | 验证码有效期（默认 5 分钟） |

### LDAP/OAuth 同步字段

| Users 字段 | LDAP 映射 | OAuth 映射 | 说明 |
|---|---|---|---|
| `username` | `uid` / `sAMAccountName` | 钉钉 `userid` / 飞书 `user_id` / 企微 `UserId` | 登录名 |
| `display_name` | `cn` / `displayName` | 钉钉/飞书/企微 字段 | 显示名 |
| `email` | `mail` | 钉钉/飞书/企微 邮箱字段 | 邮箱 |
| `phone` | `telephoneNumber` / `mobile` | 钉钉/飞书/企微 手机字段 | 手机号 |
| `employee_id` 🆕 | `employeeNumber` / `uid` | 钉钉 `userid` / 飞书 `employee_no` | 工号 |
| `department` 🆕 | 从 LDAP OU 或 `departmentNumber` 解析 | 钉钉/飞书 部门名字段 | 部门 |
| `title` 🆕 | `title` | 钉钉 `title` / 飞书 职位字段 | 岗位 |
| `manager_id` 🆕 | 从 LDAP `manager` 属性 DN → 匹配本地用户 | — | 直属上级 |

**不同步的内容：** 角色分配、用户组成员、本地密码 — 这些由管理员在系统内配置。

---

## 六、与 v1 设计方案的关系

| 维度 | v1（现状） | v2（本方案） | 变更 |
|---|---|---|---|
| 权限模型 | 26 个权限码直绑 User（扁平） | Role → Permission（角色继承） | 新增 Role 表 |
| 实例隔离 | User → ResourceGroup → Instance | UserGroup → ResourceGroup → Instance | 新增 UserGroup，移除 user_resource_group |
| 查询授权 | QueryPrivilege 仅授权给用户 | 支持授权给用户或用户组 | 扩展 QueryPrivilege |
| 授权粒度 | 实例 + 库 + 表 | 资源组 + 实例 + 库 + 表 | 新增 scope_type |
| 审批流 | 指定用户 / 资源组 / 任意审批人 | 新增直属上级 / 用户组 / 角色持有者 | ApprovalFlowNode 扩展 |
| DBA 角色 | 无（is_superuser 或扁平权限码） | dba（全局）/ dba_group（资源组内） | 新增 Role |
| 用户信息 | 无工号/部门/岗位/直属上级 | 新增4个字段 | Users 表扩展 |
| 认证方式 | 密码 + OTP + LDAP + OAuth ×4 | + 短信验证码 | SystemConfig 新增 sms 组 |

---

## 七、迁移策略

### Phase 1 — 新增表，不动旧表（零停机）

1. 新建 `role`, `user_group`, `user_group_member`, `role_permission`, `group_resource_group` 表
2. `sql_users` 新增 `role_id`, `manager_id`, `employee_id`, `department`, `title` 列（nullable）
3. `query_privilege` 新增 `user_group_id`, `scope_type`, `resource_group_id` 列（nullable）
4. Alembic 迁移脚本

### Phase 2 — 数据迁移（一次性脚本，可回滚）

1. 当前 `user_permission` 记录 → 自动生成角色 + `role_permission` 记录
2. 当前 `user_resource_group` 记录 → 创建默认 UserGroup + `group_resource_group` + `user_group_member`
3. 四个内置角色及其默认权限码写入 `role` + `role_permission`

### Phase 3 — 切换逻辑（渐进切换，新旧并行）

1. `current_user` 依赖返回 `role` + `permissions` 信息
2. `require_perm()` 改为读角色的权限码集合
3. 资源组访问路径改为 用户 → 用户组 → 资源组 → 实例
4. 审批流首发切到 `manager` 节点，并为二期预留 `user_group` / `role` 扩展位
5. 前端菜单渲染改为基于角色权限码

### Phase 4 — 清理旧表 ✅

1. ~~废弃 `user_permission` 关联表~~ → 已删除表及所有代码引用
2. ~~废弃 `user_resource_group` 关联表~~ → 已删除表及所有代码引用
3. 权限获取改为仅通过 `role_permission`（`UserService.get_merged_permissions` 不再合并直接权限）
4. 资源组访问改为仅通过 `UserGroup → group_resource_group`（移除了 `Users.resource_groups` 关系）
5. `ResourceGroupService.get_member_count` 改为通过用户组计算去重成员数
6. `grant_permissions` 改为操作用户角色的 `role_permission`（无角色时自动创建专用角色）
7. 前端资源组管理改为展示关联数据库实例 + 用户组穿梭框（移除直接成员穿梭框）
8. 前端用户管理新增用户组列（显示为 Tag）
9. 前端用户组管理白屏修复（补充 Modal 组件导入）
10. 用户列表/详情 API 返回 `user_groups` 改为 `{id, name, name_cn}` 对象列表
11. 资源组列表 API 新增 `instances` 字段（关联的数据库实例列表）
12. `UserCreate`/`UserUpdate` 移除 `resource_group_ids`（资源组通过用户组关联）
13. Alembic 迁移 `0009_drop_legacy_tables.py`
14. 资源组主弹窗移除资源组级 Webhook，仅保留“实例范围 / 关联用户组 / 状态”
15. 停用资源组不能再被用户组新关联，前端选择器与后端服务层双重拦截
16. 浏览器标题统一为 `矢 准 数 据`，数据库类型显示统一为官方命名

---

## 八、概念职责边界

| 概念 | 职责 | 类比 |
|---|---|---|
| **角色（Role）** | 功能权限集合，决定能做什么操作 | 岗位（DBA、开发） |
| **用户组（UserGroup）** | 组织单位，决定审批链（谁审谁）并有组长 | 部门/团队 |
| **资源组（ResourceGroup）** | 实例访问范围，决定能操作哪些库 | 数据域 |
| **QueryPrivilege** | 细粒度数据访问，决定能查哪张表 | 表级 ACL |
| **审批流（ApprovalFlow）** | 流程定义，决定工单/权限申请的审批路径 | 审批流程 |

### 当前 UI/交互落地口径

- 资源组创建/编辑弹窗只保留：`group_name / group_name_cn / instance_ids / user_group_ids / is_active`
- 资源组级 Webhook 不再作为首发权限模型的一部分，通知主路径统一走系统配置
- 用户组编辑页只允许选择启用中的资源组；历史停用资源组仍可在列表中看到，但不会继续作为可选项
- 前端数据库类型显示统一使用官方名称：`MySQL / PostgreSQL / Oracle / TiDB / Doris / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`

---

*SagittaDB 矢准数据 · 授权体系重设计方案 v2 · 2026-04-13 · 全部 Phase 已完成*
