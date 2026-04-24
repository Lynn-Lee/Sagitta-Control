# v2-lite 权限体系本地验证清单

> 适用版本：SagittaDB v1.0-GA + v2-lite auth  
> 验证目标：确认角色权限、资源范围、查询授权、审批流和前端菜单行为与 v2-lite 设计一致。  
> 说明：完整逐项验收版请见 [v2_lite_auth_full_validation.md](./v2_lite_auth_full_validation.md)。

## 一、环境准备

### 1. 启动本地服务

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
curl -X POST http://localhost:8000/api/v1/system/init/
```

### 2. 访问地址

- 前端：`http://localhost`
- 后端 OpenAPI：`http://localhost:8000/docs`
- Flower：`http://localhost:5555`
- Grafana：`http://localhost:3000`

### 3. 默认账号

- `admin / Admin@2024!`（默认密码会触发强制改密，请先完成改密再继续权限验证）

### 4. 本轮 UI 口径

- 浏览器标题显示为 `矢 准 数 据`
- 资源组弹窗只保留“关联数据库实例 / 关联用户组 / 状态”
- 用户组编辑时不可继续关联停用资源组
- 数据库类型显示统一为 `MySQL / PostgreSQL / Oracle / TiDB / StarRocks / Doris / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
- SQL 工单提交页不再手动选择资源组，系统按权限链路自动解析
- 核心后台列表页统一了固定列宽、横向滚动和关键字段展示
- 实例管理中的数据库/Schema 同步会全量对齐当前连接用户真实可见范围
- Oracle 普通 Schema 用户只同步自己当前真实可见的 Schema，高权限账号才会同步更大范围
- 删除仍被资源组关联的实例时，系统会明确提示“请到资源组管理中移除该实例后再删除”

---

## 二、验证前置数据

建议准备以下账号和资源：

- `admin`：超级管理员
- `dev_user`：角色为 `developer`
- `group_dba_user`：角色为 `dba_group`
- `ug_dev`：开发用户组
- `rg_dev`：开发资源组
- `inst_dev_mysql`：关联到 `rg_dev` 的测试实例
- 已注册数据库：
  - `app_db`
  - `audit_db`
- 已注册表：
  - `app_db.orders`
  - `app_db.customers`

建议关系：

- `dev_user -> ug_dev`
- `ug_dev -> rg_dev`
- `rg_dev -> inst_dev_mysql`

---

## 三、角色与菜单验证

### TC-LITE-001 developer 菜单裁剪

步骤：

1. 使用 `dev_user` 登录前端。
2. 观察左侧菜单。

预期：

- 可见：`Dashboard`、`SQL 工单`、`在线查询`
- 不可见：`可观测中心`、`运维工具`、`系统管理`、`审计日志`

### TC-LITE-002 页面级权限兜底

步骤：

1. 使用 `dev_user` 登录。
2. 直接访问 `http://localhost/system/users` 或 `http://localhost/monitor`。

预期：

- 页面返回 403 提示
- 不应进入实际功能页

### TC-LITE-003 dba_group 菜单能力

步骤：

1. 使用 `group_dba_user` 登录。
2. 查看左侧菜单。

预期：

- 可见：`Dashboard`、`SQL 工单`、`在线查询`、`可观测中心`、`运维工具`、`审计日志`
- 不应具备超管级全局能力

---

## 四、资源范围验证

### TC-LITE-004 developer 只能看到所属资源组实例

步骤：

1. 使用 `dev_user` 登录。
2. 进入在线查询、工单提交、查询权限申请页面。
3. 打开实例下拉框。

预期：

- 只能看到 `rg_dev` 关联的实例
- 看不到组外实例

### TC-LITE-005 dba_group 只能操作所属资源组实例

步骤：

1. 使用 `group_dba_user` 登录。
2. 尝试访问组外实例的详情、数据库列表、监控配置。

预期：

- 组外实例访问被拒绝
- 组内实例操作正常

### TC-LITE-005C 删除被资源组关联的实例会被阻止

步骤：

1. 使用 `admin` 打开“实例管理”。
2. 找到一个仍被资源组关联的实例。
3. 点击删除并确认。

预期：

- 实例不会被删除
- 页面提示会明确说明该实例仍被资源组关联
- 提示语包含“请到资源组管理中移除该实例后再删除”

### TC-LITE-005D 实例同步只反映当前连接用户真实可见范围

步骤：

1. 使用高权限账号创建一个 Oracle 实例并同步，确认能看到较多 Schema。
2. 将同一实例改成普通 Schema 用户账号。
3. 再次点击“从实例自动同步”。

预期：

- 同步结果会收缩到当前连接用户真实可见的 Schema
- 之前高权限账号同步进来的、当前已不可见的旧 Schema 会被自动清理

### TC-LITE-005A 停用资源组不能继续被用户组关联

步骤：

1. 使用 `admin` 将 `rg_dev` 状态切换为停用。
2. 进入“用户组管理”，编辑任一用户组。
3. 打开“关联资源组”选择框。

预期：

- `rg_dev` 不再出现在可选资源组列表中
- 若某用户组历史上已关联 `rg_dev`，列表列仍可见，并带“已停用”提示

### TC-LITE-005B SQL 工单自动解析资源组

步骤：

1. 使用 `dev_user` 登录。
2. 进入“SQL 工单 -> 提交工单”。
3. 观察表单项并选择一个自己有权限的实例和数据库。

预期：

- 表单中不再出现“资源组”选择框
- 页面会提示资源组按“用户组 -> 资源组 -> 实例”自动解析
- 对有权限的实例可以正常提交

---

## 五、查询权限验证

### TC-LITE-006 库级授权申请

步骤：

1. 使用 `dev_user` 登录。
2. 进入“查询权限”页面。
3. 申请 `inst_dev_mysql / app_db` 的库级权限。

预期：

- 申请成功
- 申请记录显示 `scope_type = database`

### TC-LITE-007 表级授权申请必须填写表名

步骤：

1. 调用 `POST /api/v1/query/privileges/apply/`
2. 传入 `scope_type=table`，但 `table_name=''`

预期：

- 请求被拒绝
- 返回“表级授权必须填写表名”类似提示

### TC-LITE-008 审批前不能查询

步骤：

1. 使用 `dev_user` 登录。
2. 在 `app_db` 执行 `SELECT * FROM orders LIMIT 1;`

预期：

- 返回 403
- 查询页出现权限排查信息

### TC-LITE-009 查询拒绝排查层级

步骤：

1. 使用 `dev_user` 执行无权限查询。
2. 观察查询页错误提示。
3. 或直接调用 `POST /api/v1/query/access-check/`

预期：

- 能看到 `layer`
- 取值应为 `resource_scope` 或 `data_scope`

### TC-LITE-010 库级授权生效

步骤：

1. 使用 `admin` 或有 `query_review` 权限的用户审批通过库级申请。
2. 使用 `dev_user` 再次查询 `app_db.orders`。

预期：

- 查询通过

### TC-LITE-011 表级授权仅放行目标表

步骤：

1. 只给 `dev_user` 授权 `app_db.orders`
2. 分别查询 `orders` 和 `customers`

预期：

- `orders` 可查
- `customers` 仍返回 403

---

## 六、审批流验证

### TC-LITE-012 审批流页面只允许 3 种节点类型

步骤：

1. 使用 `admin` 进入“系统管理 → 审批流管理”。
2. 新建或编辑流程。

预期：

- 节点类型只显示：
  - `指定用户`
  - `直属上级`
  - `任意审批员`

### TC-LITE-013 指定用户审批节点

步骤：

1. 新建审批流，节点类型选择“指定用户”。
2. 不填写审批人，尝试保存。

预期：

- 后端校验失败
- 返回“approver_type=users 时必须填写 approver_ids”类似提示

### TC-LITE-014 直属上级审批

步骤：

1. 给 `dev_user` 配置 `manager_id`
2. 创建“直属上级”审批节点
3. 触发审批

预期：

- 只有对应直属上级可审批

---

## 七、监控与实例管理验证

### TC-LITE-015 dba_group 监控范围

步骤：

1. 使用 `group_dba_user` 登录。
2. 进入“可观测中心”。

预期：

- 只能看到所属资源组实例的监控配置
- 不能配置组外实例

### TC-LITE-016 实例管理范围约束

步骤：

1. 使用非超管、非全局实例权限用户尝试更新组外实例。

预期：

- 返回 403

---

## 八、建议的 API 快速核对

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/system/init/
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin@2024!"}'
```

若返回 `password_change_required=true`，先按返回的 `password_change_token` 调用强制改密接口，之后再使用新密码获取正式 Token。

查询权限排查：

```bash
curl -X POST http://localhost:8000/api/v1/query/access-check/ \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "instance_id": 1,
    "db_name": "app_db",
    "sql": "select * from orders limit 1",
    "limit_num": 100
  }'
```

---

## 九、通过标准

以下条件全部满足，可认为本地 v2-lite 权限验证通过：

- 菜单显示与权限码一致
- 页面直接访问有 PermissionGuard 兜底
- 用户实例可见性符合 `UserGroup -> ResourceGroup -> Instance`
- 查询授权只支持库级 / 表级
- 查询拒绝能定位层级
- 审批流只支持 `users / manager / any_reviewer`
- `dba_group` 不具备全局实例能力
- 停用资源组不能继续被用户组新关联
- 浏览器标题和数据库类型显示名符合当前 UI 规范
