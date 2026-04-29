# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Overview

SagittaDB 矢准数据 — 企业级多引擎数据库管控平台（重构自 Archery v1.14.0）。  
当前版本：**v1.0-GA + v2-lite 授权体系**，内测中。

**Stack**: FastAPI 0.110 + SQLAlchemy 2.0 async + Alembic + Celery 5 + PostgreSQL 16 (backend)  
React 18 + Vite 5 + TypeScript + Ant Design 5 + TanStack Query v5 + Zustand (frontend)

---

## Commands

### Full Stack (Docker — recommended)

```bash
# 根目录
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head

# 服务地址
# API + Swagger: http://localhost:8000/docs（仅 APP_ENV=development 时可访问）
# Frontend:      http://localhost
# Flower:        http://localhost:5555
# Prometheus:    http://localhost:9090
# Grafana:       http://localhost:3000
```

### Backend (standalone — from `backend/`)

```bash
pip install -e ".[dev]"

# 运行
uvicorn app.main:app --reload --port 8000

# 数据库迁移（当前 head: 0032_notification_delivery）
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1

# Celery（需分开开三个终端）
celery -A app.celery_app worker -Q default,execute,notify,archive,monitor --loglevel=info
celery -A app.celery_app beat --loglevel=info          # 定时任务
celery -A app.celery_app flower --port=5555            # Web 监控

# 代码质量
ruff format . && ruff check . && mypy app/

# 测试（需要 sagittadb_test 数据库已存在）
pytest tests/unit/ -v --cov=app --cov-fail-under=35   # 单元测试（152个，覆盖率门限35%）
pytest tests/integration/ -v                           # 集成测试（31个）
pytest tests/unit/test_auth.py::test_hash_password     # 单个测试
pytest tests/ -k "keyword"                             # 按关键字过滤
locust -f tests/perf/locustfile.py --host http://localhost:8000  # 性能测试
```

### Frontend (standalone — from `frontend/`)

```bash
npm install
npm run dev          # http://localhost:5173（需配置 VITE_API_BASE_URL 或代理到 :8000）
npm run build        # tsc + vite build → dist/
npm run lint
npm run typecheck
```

---

## Architecture

### 请求完整链路

```
浏览器 → Nginx(:80) [静态文件 + 反向代理] → FastAPI(:8000)
                                                  ↓
                                          JWT 黑名单检查（Redis）
                                          current_user 依赖注入
                                                  ↓
                              ┌──────────────────────────────────┐
                              │  同步操作                         │  异步操作
                              │  → services/ → engines/          │  → Celery task → Redis → Worker
                              │  → PostgreSQL（asyncpg）         │  → Worker 独立创建 AsyncEngine
                              └──────────────────────────────────┘
```

所有 SQL 执行（工单、归档、监控采集）都通过 Celery 任务异步执行，router 立即返回 job ID。

### Backend (`backend/app/`)

```
core/
  config.py       pydantic-settings 读环境变量。
                  ⚠️ 认证(LDAP/OAuth)、通知(钉钉/飞书/企微/邮件)、AI 等
                  运行时配置均在 SystemConfig DB 表，不在环境变量。
  security.py     密码哈希: SHA-256 → base64 → bcrypt(rounds=12)（规避72字节限制）
                  Fernet 加密: key = base64(SHA-256(SECRET_KEY))
                  ⚠️ SECRET_KEY 变更 → 所有 Fernet 加密数据（实例密码/SSH密钥/敏感配置）无法解密
  deps.py         current_user: JWT → Redis黑名单校验(fail-close) → 加载 Role+UserGroup → 返回 dict
                  require_perm("codename"): 工厂函数，superuser 短路
  database.py     AsyncEngine + get_db() dependency（FastAPI 专用，不跨进程共享）

engines/
  protocol.py     EngineProtocol（typing.Protocol，非 ABC）— 结构化子类型
  registry.py     get_engine(instance) — importlib 延迟加载，_REGISTRY dict 分发
                  新增引擎只需在 _REGISTRY 加一行
  models.py       ResultSet / ReviewSet — 所有引擎返回的统一类型
  mysql.py        完整实现（aiomysql 连接池，含 DictCursor 修复）
  pgsql.py        完整实现（asyncpg）
  mongo.py        完整实现（motor，含 processlist/metrics）
  redis.py        完整实现（白名单安全控制，16数据库，INFO指标）
  clickhouse.py   完整实现（clickhouse-connect HTTP协议）
  oracle.py / mssql.py / cassandra.py / elasticsearch.py / doris.py  骨架已有，待真实环境验证

models/           SQLAlchemy ORM（mapped_column 风格）
  base.py         BaseModel: tenant_id(SaaS预留=1) + created_at + updated_at
  user.py         Users + ResourceGroup + Permission
                  v2: Users 新增 role_id / manager_id / employee_id / department / title
  role.py         Role + UserGroup（含 leader_id/parent_id 树形层级）
                  关联表: role_permission / user_group_member / group_resource_group
  instance.py     Instance + InstanceDatabase（解耦实例连接与库名）+ SshTunnel + InstanceTag
  workflow.py     SqlWorkflow + WorkflowStatus(IntEnum 0-8) + WorkflowAudit + SqlWorkflowContent
  approval_flow.py ApprovalFlow + ApprovalFlowNode（支持 users/manager/any_reviewer 三种审批类型）
  query.py        QueryPrivilege + QueryPrivilegeApply + QueryLog
  masking.py      MaskingRule + WorkflowTemplate
  monitor.py      MonitorCollectConfig + MonitorPrivilegeApply + MonitorPrivilege
  system.py       SystemConfig（KV 存储，9个配置分组）+ OperationLog + NotificationDeliveryLog

services/         纯 Python 业务逻辑，接受 db session 参数，不自建 session
  masking.py      sqlglot 解析 SELECT 列 → 匹配脱敏规则（替代 goInception，支持20+方言）
  audit.py        操作日志写入 operation_log
  rollback.py     sqlglot 静态逆向 SQL + my2sql 命令生成 + PG WAL 查询语句
  text2sql.py     自然语言→SQL（Codex API，_DEFAULT_MODEL = Codex-sonnet-4-20250514）
  notify.py       主动通知服务：审批/执行事件、收件人解析、飞书/企微/钉钉应用消息、邮件兜底、Webhook 兼容
  sms_auth.py     短信验证码（阿里云/腾讯云/自定义HTTP，Redis限流60s/天10次）
  approval_flow.py 审批流模板 CRUD + snapshot_for_workflow()（工单创建时快照节点）
  system_config.py 9个配置分组管理，敏感字段 Fernet 加密，update_batch 返回 change_summary
  ldap_auth.py    LDAP 三步验证: service bind → 搜索用户 → user re-bind 密码验证
  oauth_auth.py   钉钉/飞书/企微/CAS OAuth2，state 存 Redis(5min TTL) 防 CSRF

tasks/            Celery tasks（5个队列：default/execute/notify/archive/monitor）
  execute_sql.py  工单 SQL 异步执行
                  ⚠️ 必须自建 AsyncEngine，不能复用 FastAPI 的 engine（跨进程）
  archive.py      数据归档（purge/dest 模式，分批执行）
  monitor.py      监控指标采集
  notify.py       通知任务（send_notification_event，notify 队列）
```

### v2-lite 授权体系（当前落地版本）

```
权限链路: User → role_id → Role → role_permission → Permission(codename)
资源链路: User → user_group_member → UserGroup → group_resource_group → ResourceGroup → Instance

旧表（已在 migration 0009 删除）: user_permission / user_resource_group
⚠️ 代码中已无对这两张旧表的任何引用
```

**四个内置角色**（`is_system=True`，不可删除）：

| role.name | 特征 |
|---|---|
| `superadmin` | `is_superuser=True`，绕过所有检查 |
| `dba` | `query_all_instances` + `monitor_all_instances`，全局运维 |
| `dba_group` | 运维权限，实例范围限于所在资源组 |
| `developer` | `sql_submit` + `query_submit` + `query_applypriv` |

**在线查询三层校验**：

```
L0: InstanceDatabase.is_active 检查（False → 403，普通用户 API 过滤不可见）
L1: is_superuser 或 query_all_instances → 放行
L2: 实例是否在用户的资源组内（UserGroup → ResourceGroup → Instance）
L3: QueryPrivilege 库级/表级授权（valid_date 有效期控制）
```

**工单审批流快照**：工单创建时将 ApprovalFlowNode 快照到 `WorkflowAudit.audit_auth_groups_info`（JSON），此后修改审批流模板不影响在途工单。

### Alembic 迁移历史（当前已到 0032）

```
0001_initial_schema        — 初始完整表结构
0002_system_config         — SystemConfig + OperationLog
0003_fix_totp_secret       — totp_secret 字段从100扩展到500
0004_instance_database     — InstanceDatabase 表
0005_approval_flow         — ApprovalFlow + ApprovalFlowNode + workflow.flow_id FK
0006_role_usergroup_v2     — Role / UserGroup / 关联表（v2授权体系第一阶段）
0007_query_priv_v2         — QueryPrivilege v2 字段扩展
0008_approval_flow_v2      — ApprovalFlowNode v2 字段扩展
0009_drop_legacy_tables    — 删除 user_permission / user_resource_group（Phase 4清理）
0010_query_priv_apply_flow — QueryPrivilegeApply.flow_id FK
0011_workflow_template_v1  — 工单模板表
0012_seed_default_workflow_templates — 默认工单模板初始化
0013_user_password_policy  — 用户密码策略与轮换字段
0014_query_privilege_revoke_audit — 查询权限撤销审计字段
0015_priv_revoke_backfill  — 查询权限撤销历史回填
0016_workflow_execution_decision — 工单执行决策字段
0017_query_log_history_audit — 查询历史字段（操作类型/导出格式/用户名/实例快照/IP/错误）
0018_qlog_snapshot_backfill — 历史 query_log 用户名/实例名/DB 类型回填
0019_session_snapshot — 会话采样快照
0020_slow_query_log — SQL 洞察日志
0021_slow_query_v2 — 慢 SQL v2 字段扩展
0022_session_collect_config — 会话采集配置
0023_archive_jobs — 数据归档作业与批次日志
0024_session_duration_ms — 会话时长毫秒字段
0025_session_duration_fields — 会话时长字段拆分
0026_submission_risk_plan — 提交风险预案
0027_high_risk_sql_submit_permission — 高危 SQL 提交权限
0028_archive_execute_permission — 数据归档执行权限
0029_native_observability — 原生观测采集
0030_observability_permission_rework — 观测权限重构
0031_sql_activity_collect_semantics — SQL 活动采集语义
0032_notification_delivery — 用户外部通知身份 + notification_delivery_log
```

### Frontend (`frontend/src/`)

```
api/
  client.ts     axios 实例（baseURL=/api/v1），含 JWT 自动注入 + 401 自动刷新
                Token 刷新时用 pendingQueue 队列缓存并发请求，刷新完毕后统一重发
  auth.ts / instance.ts / workflow.ts / query.ts / system.ts / approvalFlow.ts

store/
  auth.ts       Zustand persist（localStorage key: 'sagittadb-auth'）
                hasPermission() 内置 superuser 短路

pages/          按功能域分目录（workflow/ query/ monitor/ system/ instance/...）
components/
  AuthGuard.tsx     未登录重定向到 /login
  PermissionGuard   按权限码控制页面访问
  MainLayout.tsx    侧边菜单（按权限码过滤）
```

**前端环境变量**：`VITE_API_BASE_URL`（开发时代理到 `:8000`，生产时留空走 Nginx 同源代理）

### 环境变量（关键）

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | asyncpg，FastAPI + Celery Worker 使用 |
| `DATABASE_URL_SYNC` | psycopg2，**仅 Alembic** 使用 |
| `REDIS_URL` | Celery broker + Token 黑名单 |
| `SECRET_KEY` | JWT 签名 + Fernet 加密密钥派生，**生产环境不可更改否则加密数据全失效** |
| `APP_ENV` | `development`（开启 /docs）/ `production`（阻断默认 SECRET_KEY 启动） |
| `ENABLE_GOINCEPTION` | 可选 MySQL SQL 审核增强，默认 false |

所有认证/通知/AI 配置（LDAP、OAuth、钉钉、飞书、企微、邮件、Anthropic API Key）均在  
`SystemConfig` 表（9个分组）通过 `/api/v1/system/config` 接口管理，**无需重启服务**。

### 数据安全设计

- **密码哈希**：`SHA-256(password)` → `base64` → `bcrypt(rounds=12)`（规避 bcrypt 72字节截断）
- **字段加密**：`Fernet`，密钥由 `base64(SHA-256(SECRET_KEY))` 派生  
  加密范围：`Instance.password`、`SshTunnel.password/private_key`、`SystemConfig` 敏感项
- **Token 黑名单**：logout 时写入 Redis，`current_user` 每次请求检查；Redis 不可达时返回 503（fail-close，不放行）
- **查询注入防御**：引擎层强制参数化查询，禁止字符串拼接，`filter_sql()` 注入 LIMIT

### Tests

```
tests/
  unit/           152 个单元测试（完全 mock，不依赖真实 DB）
    test_auth.py              密码哈希/JWT/Fernet 加密/Schema 验证
    test_masking.py           sqlglot 列提取/脱敏规则
    test_engine_registry.py
    test_mysql_engine.py / test_mongo_engine.py
    test_ldap_auth.py / test_oauth_auth.py
    test_rollback.py          sqlglot 逆向SQL / my2sql / PG WAL
    test_notify.py            钉钉/飞书/企微 mock HTTP、通知失败不中断主流程
    test_system_config.py     配置服务/敏感字段加密
    test_workflow_service.py  工单状态/审批链路
    test_authz_v2_lite.py     v2-lite 授权链路（13个测试）

  integration/    31 个集成测试（需要真实 PostgreSQL sagittadb_test 库 + Redis）
    conftest.py   每个测试独立创建 AsyncEngine（避免 asyncpg 跨 event loop 错误）
                  admin 默认密码: Admin@2024!，首次通过 POST /api/v1/system/init/ 初始化
    test_health / test_auth_api / test_instance_api / test_workflow_api

  perf/
    locustfile.py  Locust 性能测试（AuthUser + APIUser）
```

**CI 覆盖率门限：35%**（`--cov-fail-under=35`）

### CI/CD

- `ci.yml`：后端（ruff lint + mypy + 单元测试 + 集成测试） + 前端（typecheck + lint + build） + Docker 构建验证
- `security.yml`：每周一 + main push 触发；Bandit SAST + pip-audit + Trivy 容器扫描 + CodeQL
- main 分支 push 后自动构建并推送 GHCR（`ghcr.io/{repo}-backend:latest`、`ghcr.io/{repo}-frontend:latest`）

### 生产部署

```bash
# Docker Compose 生产版
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Kubernetes + Helm
cd deploy/helm
helm dependency update sagittadb/
helm install sagittadb sagittadb/ -f sagittadb/values-prod.yaml
# initContainer 自动执行 alembic upgrade head

# 数据库备份
deploy/backup/backup-postgres.sh    # pg_dump + gzip + S3 上传
deploy/backup/restore-postgres.sh   # 从本地或 S3 URI 恢复（交互确认）
```

### 已知待验证项（Pack E 引擎）

Elasticsearch / MSSQL / Cassandra / Doris 引擎骨架已实现但未在真实环境验证。处理这些引擎时需格外小心，建议先用 `test_connection()` 验证连通性。

### 关键技术决策

| 决策项 | 说明 |
|---|---|
| SQL 解析 | sqlglot 替代 goInception（20+方言，零外部进程依赖）|
| 引擎协议 | `typing.Protocol`（非 ABC），静态类型检查，注册表 importlib 延迟加载 |
| 工单状态 | IntEnum 0-8（0=待审核，6=成功，7=异常，8=取消）|
| 数据库注册 | InstanceDatabase 表解耦实例连接与库名；Oracle→Schema，Redis→数字索引 |
| OAuth2 | 后端处理 code 换 token → 重定向前端携带 token，前端无需接触 client_secret |
| 审批人类型 | `users`（指定用户 ID 列表）/ `manager`（直属上级 manager_id）/ `any_reviewer`（任意审批员）；通知解析还兼容 `user_group` / `role` / `group` |
| 归档实现 | 纯 Python 通过引擎层执行，不依赖 pt-archiver，各 DB 分批语法独立适配 |
| AI Text2SQL | `Codex-sonnet-4-20250514`，配置从 SystemConfig 读 API Key |

---

## 数据模型快速参考

| 表名 | 说明 |
|---|---|
| `sql_users` | 用户（v2新增 role_id/manager_id/employee_id/department/title；通知新增 dingtalk_user_id/feishu_open_id/wecom_userid）|
| `role` / `permission` / `role_permission` | v2角色权限体系（替代旧 user_permission）|
| `user_group` / `user_group_member` | 用户组（含 leader_id/parent_id 树形层级）|
| `group_resource_group` | 用户组↔资源组（替代旧 user_resource_group）|
| `resource_group` / `instance_resource_group` | 资源组↔实例 |
| `sql_instance` | 实例（密码 Fernet 加密）|
| `instance_database` | 实例下注册的库（is_active 控制启停可见性）|
| `ssh_tunnel` | SSH 跳板机配置 |
| `sql_workflow` | 工单主表（含 flow_id FK）|
| `sql_workflow_content` | 工单 SQL 内容（大字段分离）|
| `workflow_audit` | 审批日志（audit_auth_groups_info 存快照 JSON）|
| `approval_flow` / `approval_flow_node` | 多级审批流模板 |
| `query_privilege` / `query_privilege_apply` | 查询权限及申请 |
| `query_log` | 查询/导出历史（operation_type/export_format/username/instance_name/db_type/client_ip/error + priv_check/hit_rule/masking）|
| `masking_rule` | 数据脱敏规则（7种内置类型+自定义正则）|
| `workflow_template` | 工单模板（公开/私有，use_count 统计）|
| `monitor_collect_config` | 原生监控采集配置（启停/采集间隔/容量间隔/保留天数；历史 Exporter 字段保留兼容）|
| `monitor_metric_snapshot` | 实例级监控指标采样（健康/连接/吞吐/慢查询/锁等待/容量/诊断）|
| `monitor_database_capacity_snapshot` | 库/Schema 容量采样 |
| `monitor_table_capacity_snapshot` | 表/索引容量采样 |
| `system_config` | 系统配置 KV（9个分组，敏感值 Fernet 加密）|
| `operation_log` | 操作审计日志 |
| `notification_delivery_log` | 主动通知投递日志（事件/对象/渠道/收件人/状态/错误）|
