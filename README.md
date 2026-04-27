# SagittaDB 矢准数据

> **矢向数据，精准管控**
> 企业级多引擎数据库管控平台 · 基于 Archery v1.14.0 深度重构 · v1.0-GA + v2-lite 权限收敛

---

## 产品简介

SagittaDB 通过统一的 Web 界面，帮助 DBA 和研发团队安全、高效地完成 SQL 审核上线、在线查询、慢日志分析、数据库监控等全流程数据库管理工作。

- **安全**：修复原 Archery 5 个 P0 安全漏洞，Token 黑名单 fail-close，敏感字段加密存储，并内置本地密码复杂度、默认密码强制改密和 30 天轮换策略
- **全面**：支持 11 种数据库引擎（MySQL / PostgreSQL / Oracle / MongoDB / Redis / ClickHouse 等）
- **高效**：AI Text2SQL + SQL 工单模板 + 自定义审批流，全异步 Celery 执行不阻塞
- **可观测**：内建数据库原生指标采集、容量/表索引体积监控与全流程操作审计
- **可解释权限**：v2-lite 权限体系已落地，权限拒绝可定位到身份 / 资源范围 / 数据授权层

## 技术栈

| 层次 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 async + Celery 5 + PostgreSQL 16 |
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 |
| SQL 解析 | sqlglot（替代 goInception，支持 20+ 方言） |
| AI | Anthropic Claude API（Text2SQL） |
| 可观测 | 数据库原生采集 + Celery monitor 队列 + PostgreSQL 指标快照（Prometheus/Grafana 可选部署） |
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
# Grafana：    http://localhost:3000（可选外围监控服务）
# Flower：     http://localhost:5555
```

## Oracle 11g 连接说明

SagittaDB 的 Oracle 驱动基于 `python-oracledb`。如果目标库是 `Oracle 11.2` 或更早版本，必须启用 Thick 模式并提供 Oracle Instant Client；仅用默认 Thin 模式会报 `DPY-3010`。

推荐做法：

```bash
# 1. 将 Oracle Instant Client 解压到后端构建上下文
# 例如：backend/vendor/oracle/instantclient_19_27/

# 2. 在 .env 中启用 Thick 模式
ORACLE_DRIVER_MODE=thick

# 3. 重新构建并启动
docker compose build backend celery_worker celery_beat flower
docker compose up -d
```

补充说明：

- Linux 容器中通常不需要额外设置 `ORACLE_CLIENT_LIB_DIR`；镜像构建时会自动把 `/opt/oracle/instantclient` 加入动态库搜索路径。
- 如果你的 Oracle 是 `12.1+`，可以继续使用 `ORACLE_DRIVER_MODE=thin` 或默认的 `auto`。

## 目录结构

```
SagittaDB/
├── backend/        # FastAPI 后端（engines / routers / services / models）
├── frontend/       # React 前端（pages / components / store / api）
├── deploy/         # 部署配置（Nginx / 可选 Prometheus / Grafana）
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
| 会话诊断与慢日志分析 | 在线/历史会话、慢日志采集配置、SQL 指纹聚合、MySQL/PG 执行计划分析 | ✅ 100% |
| 原生可观测中心 | 数据库实例指标、库容量、表/索引容量、采集诊断，不依赖 Prometheus/Grafana | ✅ 100% |
| Bug 修复 | MySQL DictCursor 修复、PG 表缺失修复、前端下拉框截断修复 | ✅ 100% |

**总体完成度：100%（v1.0-GA）**

详细进度请见 [docs/sagittadb_progress.md](docs/sagittadb_progress.md)
产品需求文档请见 [docs/sagittadb_prd.md](docs/sagittadb_prd.md)
权限设计与收敛方案请见 [docs/sagittadba_auth_redesign_v2.md](docs/sagittadba_auth_redesign_v2.md)

## 数据字典近况

- 数据字典已从“字段浏览”扩展为“字段 + 约束详情 + 索引信息”三块联动展示。
- 当前关系型数据库优先支持：`MySQL / TiDB / StarRocks / PostgreSQL / Oracle / MSSQL`。
- 表字段详情页已针对长默认值、长注释做了单行省略、悬浮查看与横向滚动优化，避免长文本挤压列名换行。
- PostgreSQL / Oracle 的列注释链路已补齐：数据字典会直接展示 `column_comment`，DDL 预览也会追加对应的 `COMMENT ON COLUMN ...` 语句。
- 后端新增了统一元数据归一化层，前端无需按数据库类型分别适配约束/索引字段名。
- 列级约束摘要已统一收敛为：`主键 / 非空 / 唯一 / 唯一索引 / 联合唯一`；单列 `IS NOT NULL` 型 `CHECK` 只在列上体现，不再在“约束详情”重复展示。
- 复合唯一/复合唯一索引会在参与列上显示 `联合唯一`，并通过悬浮提示说明所属联合列组，避免误解为“单列唯一”。
- 数据字典访问不再独立申请权限，已通过的查询权限会自动继承相同范围的数据字典可见权；查询权限现已支持 `instance / database / table` 三级粒度。
- 数据字典菜单已从运维工具中拆出为独立权限 `menu_schema`；`developer` 默认可见该菜单，但仍受实例范围和查询权限约束。
- 数据字典数据库列表会对齐实例管理中的库启停状态：禁用库显示 `已禁用`；普通用户不可选，超管与具备 `query_all_instances` 的 DBA 可继续查看。
- 这条链路已补齐引擎 SQL、服务层、API 路由、前端渲染四层单测。

## 权限体系（v2-lite）

当前权限体系采用 5 层职责拆分：

1. `is_superuser`：身份层，超管直接绕过检查。
2. `Role -> Permission`：功能权限层，决定能做什么。
3. `UserGroup -> ResourceGroup -> Instance`：资源范围层，决定能看到哪些实例。
4. `QueryPrivilege(instance|database|table)`：数据授权层，首发仅支持授权给用户本人。
5. `ApprovalFlow(users|manager|any_reviewer)`：审批流层，决定谁来审。

首发范围内已落地的关键行为：

- 前端菜单和页面访问统一按权限码渲染与拦截
- `developer` 默认不显示监控、运维、系统管理入口
- `dba_group` 不具备全局实例能力，只在所属资源组范围内工作
- 查询权限支持实例级 / 库级 / 表级，且必须先通过实例范围校验
- 查询权限审批通过后会自动继承相同范围的数据字典查看权限
- PostgreSQL 在线查询已支持非 `public` schema：表名在库内唯一时可直接申请/查询 `table_name`；若同名表存在于多个 schema，必须使用 `schema.table_name`
- 查询拒绝时可通过 `POST /api/v1/query/access-check/` 返回拒绝层级与原因
- 本地账号密码登录会校验密码安全策略：至少 8 位，包含数字、大写字母、小写字母和特殊字符；默认密码、弱密码或超过 30 天未修改时，仅签发短效改密令牌并要求改密后重新登录；到期前 7 天在登录后全局提示
- 用户管理支持 Excel / CSV 批量导入导出，导出文件可直接修改后回灌
- 用户批量导入界面的默认密码示例已调整为 `Sagitta@2026A`，与系统密码复杂度保持一致
- 用户管理页内支持统一筛选与直接导出：关键词（含电话号码）、角色、用户组、部门、职位、状态
- 用户组管理支持 Excel / CSV 批量导入导出，支持模板下载、失败记录导出与回灌更新
- 用户组管理页内支持统一筛选与直接导出：组标识 / 中文名、组长、上级组、关联资源组、状态
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
    - 实例类型展示名统一使用规范命名：`MySQL / PostgreSQL / Oracle / TiDB / StarRocks / Doris / MSSQL / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
  - 全部统计按当前登录用户权限范围裁剪，模块内部统一使用同一个时间范围（`7/14/30/60` 天 + 自定义天数）
  - 审批相关排行与统计反映“当前权限范围内业务对象涉及的审批处理”，不等同于当前登录人的个人待办/已办工作量

## 运维诊断近况

- 会话管理已重做为连接/会话视角：在线会话默认展示完整连接清单（含空闲连接），SQL 仅作为会话上下文；前端展示连接时长、状态时长、当前操作时长和事务时长，并支持隐藏空闲会话。
- 历史会话分为平台采样快照和 Oracle ASH/AWR 活跃采样：周期性 `collect_session_snapshots` 会写入 `session_snapshot`，前端可按实例、来源、用户、数据库、状态、命令、SQL 关键字和多种时长筛选历史会话。
- TiDB 已拆为独立 `TidbEngine`，复用 MySQL 协议连接能力但使用 TiDB 专属会话采集，优先读取 `information_schema.CLUSTER_PROCESSLIST`。
- 慢日志分析已升级到 v2：新增 `slow_query_log` 与 `slow_query_config`，支持平台查询历史同步、MySQL/PG/Redis 原生采集、SQL 指纹聚合、实例级采集配置和最近采集状态。
- MySQL / PostgreSQL 慢 SQL 详情支持执行计划分析：MySQL 使用 `EXPLAIN FORMAT=JSON`，PostgreSQL 使用 `EXPLAIN (FORMAT JSON, BUFFERS, VERBOSE)`；其他引擎保留入口并返回明确的不支持提示。
- 慢日志页面包含 `总览 / 慢 SQL 明细 / 指纹聚合 / 实时慢查询 / 采集配置`，指纹详情展示趋势、实例/库/用户/来源分布、结构化优化建议和样例 SQL。
- 数据归档已升级为审批作业：提交后生成归档审批工单，审批通过后由 Celery `archive` 队列分批执行，并支持暂停、继续、取消和批次日志查看。
- 新增 Alembic 迁移：`0019_session_snapshot`、`0020_slow_query_log`、`0021_slow_query_v2`、`0022_session_collect_config`、`0023_archive_jobs`、`0024_session_duration_ms`、`0025_session_duration_fields`。
- 详细说明见 [docs/slowlog_diagnostic_v2.md](docs/slowlog_diagnostic_v2.md)。

## 最近验证

本次 v2-lite 收敛相关验证已通过：

```bash
cd frontend && npm run typecheck
cd backend && python3 -m compileall app
cd backend && ./.venv/bin/python -m pytest tests/unit/test_auth.py
cd backend && ./.venv/bin/python -m pytest tests/unit/test_authz_v2_lite.py
cd backend && ./.venv/bin/python -m pytest tests/unit/test_session_diagnostic.py tests/unit/test_slowlog_service.py -q
cd frontend && ./node_modules/.bin/eslint src/pages/diagnostic/DiagnosticPage.tsx src/api/diagnostic.ts src/pages/slowlog/SlowlogPage.tsx src/api/slowlog.ts --ext ts,tsx --report-unused-disable-directives --max-warnings 0
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
- 在线查询页已重构为三段式工作台：左侧表浏览器、中间 SQL 编辑器、底部 `DDL 预览 / 结果` Tab；选择表后自动刷新 DDL 预览，表浏览器标题行保留 `插入表名`，底部支持 `复制 DDL`
- 在线查询新增 `查询历史` 页面：按现有 v2-lite 查询治理范围展示“谁在何时执行/导出了什么 SQL、多少行、耗时、是否脱敏、来源 IP、是否失败”
- 在线查询导出已统一改为后端导出留痕，`查询` / `导出` 成功与失败都会写入 `query_log`；新增 Alembic 迁移 `0017_query_log_history_audit` 与 `0018_qlog_snapshot_backfill`
- DDL 预览支持 `简化 DDL / 原始 DDL` 双模式：默认给开发人员更简洁、可迁移的简化版本，Oracle 原始 DDL 保留 `DBMS_METADATA.GET_DDL` 输出供 DBA 查看；PostgreSQL 简化 DDL 会追加普通索引定义并跳过主键/唯一约束重复索引
- 浏览器标题统一为 `矢 准 数 据`
- 密码安全策略已下沉到所有本地用户：创建用户、批量导入、个人改密、登录强制改密都使用同一套复杂度规则；`password_changed_at` 支持 30 天过期与 7 天到期提醒
- 登录页强制改密流程改为页内表单，提示文案会完整展示长度、数字、大小写字母、特殊字符和 30 天轮换要求
- 顶部右侧用户入口已改为单行 flex 布局，头像/用户名不再换行；`index.html` 走 no-cache，避免强刷后仍命中旧前端资源
- 左侧主导航与系统管理子菜单已切换为统一的自定义单色 SVG 图标，并继续跟随 Ant Design 的默认尺寸、颜色与选中态机制
- `SQL 工单`、`在线查询`、`运维工具` 的子菜单图标也已切换为同一套自定义 SVG；其中“慢日志分析”图标已按视觉尺寸做过一次收紧校准，避免在侧栏中显得偏小
- 业务弹窗与业务抽屉已统一关闭遮罩点击自动关闭；用户点击黑色遮罩不再误关表单，但仍保留右上角 `X`、`Esc` 与取消按钮等显式关闭方式
- 前端数据库类型显示统一为官方命名：`MySQL / PostgreSQL / Oracle / TiDB / StarRocks / Doris / ClickHouse / MongoDB / Cassandra / Redis / Elasticsearch / OpenSearch`
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
