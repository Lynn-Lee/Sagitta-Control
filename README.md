# SagittaDB 矢准数据

> **矢向数据，精准管控**
> 企业级多引擎数据库管控平台 · 基于 Archery v1.14.0 深度重构 · v1.0-GA + v2-lite 权限收敛

---

## 产品简介

SagittaDB 通过统一的 Web 界面，帮助 DBA 和研发团队安全、高效地完成 SQL 审核上线、在线查询、慢日志分析、数据库监控等全流程数据库管理工作。

- **安全**：修复原 Archery 5 个 P0 安全漏洞，Token 黑名单 fail-close，敏感字段加密存储，并内置本地密码复杂度、默认密码强制改密和 30 天轮换策略
- **全面**：支持 11 种数据库引擎（MySQL / PostgreSQL / Oracle / MongoDB / Redis / ClickHouse 等）
- **高效**：AI Text2SQL + SQL 工单模板 + 自定义审批流，全异步 Celery 执行不阻塞
- **可观测**：内建 Prometheus + Grafana 监控，全流程操作审计
- **可解释权限**：v2-lite 权限体系已落地，权限拒绝可定位到身份 / 资源范围 / 数据授权层

## 技术栈

| 层次 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 async + Celery 5 + PostgreSQL 16 |
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 |
| SQL 解析 | sqlglot（替代 goInception，支持 20+ 方言） |
| AI | Anthropic Claude API（Text2SQL） |
| 可观测 | Prometheus + Alertmanager + Grafana |
| 部署 | Docker Compose（开发/测试）/ K8s + Helm（生产预留）|

## 快速启动

```bash
# 1. 复制并配置环境变量
cp .env.example .env

# 2. 启动全部服务
docker compose up -d

# 3. 执行数据库迁移
docker compose exec backend alembic upgrade head

# 4. 访问
# 前端：       http://localhost
# 后端 API：   http://localhost:8000/docs
# Grafana：    http://localhost:3000
# Flower：     http://localhost:5555
```

## 目录结构

```
SagittaDB/
├── backend/        # FastAPI 后端（engines / routers / services / models）
├── frontend/       # React 前端（pages / components / store / api）
├── deploy/         # 部署配置（Nginx / Prometheus / Grafana）
├── docs/           # 项目文档
│   ├── sagittadb_prd.md       # 产品需求文档（PRD v2.0）
│   └── sagittadb_progress.md  # 开发进度文档
└── docker-compose.yml
```

## 开发进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| Sprint 0 | 项目骨架、基础设施 | ✅ 100% |
| Sprint 1 | 认证、用户、实例管理 | ✅ 100% |
| Sprint 2 | 引擎层、在线查询、查询权限 | ✅ 100% |
| Pack A | SQL 工单全流程 + 运维工具 | ✅ 100% |
| Pack B | 可观测中心 + 迁移脚本 | ✅ 100% |
| Pack C | 系统配置、审计日志、资源组、数据库注册 | ✅ 100% |
| Pack D | 数据脱敏、数据字典、SQL 工单模板、AI Text2SQL | ✅ 100% |
| Pack E | 多引擎补全、数据归档、SQL 回滚、通知服务 | 🔧 85% |
| 品牌升级 | SagittaDB 品牌 UI 全面更新 | ✅ 100% |
| Pack F | 第三方登录（LDAP/钉钉/飞书/企微/CAS） | ✅ 100% |
| Pack G | 全链路测试、性能测试、安全扫描 | ✅ 100% |
| Pack H | Helm Chart、CI/CD、生产环境配置 | ✅ 100% |
| Security Hardening | Token 黑名单 fail-close、SECRET_KEY 强制校验、AI 路由注册 | ✅ 100% |
| 多级审批流 | v2-lite：`users / manager / any_reviewer` 已落地 | ✅ 100% |
| 数据库权限管控 | is_active 启停控制、普通用户不可见禁用库、管理员标灰"已禁用" | ✅ 100% |
| 授权体系 v2-lite | 角色权限、用户组资源范围、库/表级查询授权、权限排查接口 | ✅ 100% |
| 密码安全策略 | 复杂度校验、默认/过期密码强制改密、到期前 7 天提醒、导入默认密码合规化 | ✅ 100% |
| Bug 修复 | MySQL DictCursor 修复、PG 表缺失修复、前端下拉框截断修复 | ✅ 100% |

**总体完成度：100%（v1.0-GA）**

详细进度请见 [docs/sagittadb_progress.md](docs/sagittadb_progress.md)
产品需求文档请见 [docs/sagittadb_prd.md](docs/sagittadb_prd.md)
权限设计与收敛方案请见 [docs/sagittadba_auth_redesign_v2.md](docs/sagittadba_auth_redesign_v2.md)

## 数据字典近况

- 数据字典已从“字段浏览”扩展为“字段 + 表约束 + 索引信息”三块联动展示。
- 当前关系型数据库优先支持：`MySQL / TiDB / PostgreSQL / Oracle / MSSQL`。
- 表字段详情页已针对长默认值、长注释做了单行省略、悬浮查看与横向滚动优化，避免长文本挤压列名换行。
- 后端新增了统一元数据归一化层，前端无需按数据库类型分别适配约束/索引字段名。
- 这条链路已补齐引擎 SQL、服务层、API 路由、前端渲染四层单测。

## 权限体系（v2-lite）

当前权限体系采用 5 层职责拆分：

1. `is_superuser`：身份层，超管直接绕过检查。
2. `Role -> Permission`：功能权限层，决定能做什么。
3. `UserGroup -> ResourceGroup -> Instance`：资源范围层，决定能看到哪些实例。
4. `QueryPrivilege(database|table)`：数据授权层，首发仅支持授权给用户本人。
5. `ApprovalFlow(users|manager|any_reviewer)`：审批流层，决定谁来审。

首发范围内已落地的关键行为：

- 前端菜单和页面访问统一按权限码渲染与拦截
- `developer` 默认不显示监控、运维、系统管理入口
- `dba_group` 不具备全局实例能力，只在所属资源组范围内工作
- 查询权限只保留库级 / 表级，且必须先通过实例范围校验
- 查询拒绝时可通过 `POST /api/v1/query/access-check/` 返回拒绝层级与原因
- 本地账号密码登录会校验密码安全策略：至少 8 位，包含数字、大写字母、小写字母和特殊字符；默认密码、弱密码或超过 30 天未修改时，仅签发短效改密令牌并要求改密后重新登录；到期前 7 天在登录后全局提示
- 用户管理支持 Excel / CSV 批量导入导出，导出文件可直接修改后回灌
- 用户批量导入界面的默认密码示例已调整为 `Sagitta@2026A`，与系统密码复杂度保持一致
- 用户管理页内支持统一筛选与直接导出：关键词（含电话号码）、角色、用户组、部门、职位、状态
- SQL 工单提交页不再要求用户手动选择资源组，系统会按“用户组 → 资源组 → 实例”自动解析归属资源组
- SQL 工单列表已拆分为 `我的工单 / 审批记录 / 执行记录` 三个标签页，不同标签按提交、审批、执行视角展示不同列集
- SQL 工单详情页按真实能力字段控制按钮显示：仅当前审批节点审批人可见 `审批通过 / 驳回`
- SQL 工单列表中的 `审批链路 / 当前节点 / 状态` 已按状态统一显示规则：仅 `待审核` 显示当前节点，其他状态统一显示 `—`
- Dashboard 一期已包含三块统计模块：
  - 在线查询概览
    - 7 个卡片（查询次数 / 查询用户数 / 治理失败次数 / 脱敏次数 / 待审批 / 已通过 / 已驳回）
    - 查询趋势
    - 查询用户 Top 10
    - 治理趋势（治理失败次数包含查询执行失败，以及查询权限申请/审批失败）
    - 待审批库存趋势
  - SQL 工单概览
    - 10 个卡片（提交 / 通过 / 驳回 / 待审批 / 队列中 / 执行中 / 执行成功 / 执行失败 / 已取消 / 已完成）
    - 工单提交趋势
    - 工单治理趋势
    - 执行趋势
    - 待审批库存趋势
    - 工单提交用户 / 热点实例 / 热点数据库 / 工单相关审批人 / 执行实例 Top 10
  - 实例与库概览
    - 4 个卡片（可见实例数 / 已同步库-Schema数 / 已启用库-Schema数 / 已禁用库-Schema数）
    - 实例类型分布
    - 实例状态分布
    - 库-Schema 状态分布
    - 实例类型展示名统一使用规范命名：`MySQL / PostgreSQL / Oracle / TiDB / Doris / MSSQL / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
  - 全部统计按当前登录用户权限范围裁剪，模块内部统一使用同一个时间范围（`7/14/30/60` 天 + 自定义天数）
  - 审批相关排行与统计反映“当前权限范围内业务对象涉及的审批处理”，不等同于当前登录人的个人待办/已办工作量

## 最近验证

本次 v2-lite 收敛相关验证已通过：

```bash
cd frontend && npm run typecheck
cd backend && python3 -m compileall app
cd backend && ./.venv/bin/python -m pytest tests/unit/test_auth.py
cd backend && ./.venv/bin/python -m pytest tests/unit/test_authz_v2_lite.py
```

近期补充完成并已联调验证的权限与交互收口：

- 资源组主弹窗只保留“实例范围 + 关联用户组 + 状态”，移除了资源组级 Webhook
- 停用资源组不能再被用户组新关联，前端与后端双重拦截
- 用户组列表新增“关联资源组”列，资源组列表直接展示关联用户组标签
- 用户组列表新增“组长 / 上级组”列，列表信息与表单配置口径一致
- 实例管理中的“从实例自动同步”改为全量对齐当前连接用户真实可见的数据库/Schema，不再保留本次已不可见的旧记录
- Oracle 实例同步遵循统一规则：高权限账号可同步更多 Schema，普通 Schema 用户仅同步自己当前真实可见的 Schema
- 实例如果仍被资源组关联，删除时会被后端拒绝，并明确提示“请到资源组管理中移除该实例后再删除”
- 在线查询执行时会按当前有效查询权限真实限制返回最大行数；重复有效授权记录不再导致内部错误
- 浏览器标题统一为 `矢 准 数 据`
- 密码安全策略已下沉到所有本地用户：创建用户、批量导入、个人改密、登录强制改密都使用同一套复杂度规则；`password_changed_at` 支持 30 天过期与 7 天到期提醒
- 登录页强制改密流程改为页内表单，提示文案会完整展示长度、数字、大小写字母、特殊字符和 30 天轮换要求
- 顶部右侧用户入口已改为单行 flex 布局，头像/用户名不再换行；`index.html` 走 no-cache，避免强刷后仍命中旧前端资源
- 左侧主导航与系统管理子菜单已切换为统一的自定义单色 SVG 图标，并继续跟随 Ant Design 的默认尺寸、颜色与选中态机制
- `SQL 工单`、`在线查询`、`运维工具` 的子菜单图标也已切换为同一套自定义 SVG；其中“慢日志分析”图标已按视觉尺寸做过一次收紧校准，避免在侧栏中显得偏小
- 前端数据库类型显示统一为官方命名：`MySQL / PostgreSQL / Oracle / TiDB / Doris / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
- 核心后台表格页已统一固定列宽、横向滚动基线、长文本省略与关键业务字段展示
- 主布局已支持响应式侧栏与移动端抽屉导航，详情页会按路由映射保持菜单高亮
- 登录页、在线查询页、Dashboard 等首批高频页面已完成响应式与信息语义修正
- 前端已补齐共享 UI 骨架：`PageHeader / FilterCard / TableEmptyState / SectionLoading / SectionCard`
- 列表页、详情页、工具页和半配置页已开始统一到同一套页头、区块卡片、空态与加载态结构

## 开发指南

- 后端：[backend/README.md](backend/README.md)
- 前端：[frontend/README.md](frontend/README.md)
- 部署：[deploy/README.md](deploy/README.md)

---

*SagittaDB 矢准数据 · Full Engine Compatibility, End-to-End Observability*
