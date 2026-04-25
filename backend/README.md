# Backend — FastAPI 后端

## 开发环境启动

```bash
# 安装依赖
pip install -e ".[dev]"

# 执行数据库迁移
alembic upgrade head

# 启动开发服务器（热重载）
uvicorn app.main:app --reload --port 8000

# 启动 Celery Worker
celery -A app.celery_app worker -Q default,execute,notify,archive,monitor --loglevel=info

# 启动 Celery Beat（定时任务）
celery -A app.celery_app beat --loglevel=info

# 启动 Flower（Celery 监控）
celery -A app.celery_app flower --port=5555
```

## 数据库迁移

```bash
# 生成新迁移文件（修改 models 后执行）
alembic revision --autogenerate -m "描述变更内容"

# 应用迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1
```

## 目录说明

```
app/
├── core/         配置、数据库、安全、依赖注入、异常、日志
├── models/       SQLAlchemy ORM 模型（含 tenant_id SaaS预留）
├── schemas/      Pydantic 请求/响应 Schema（Sprint 1+ 补充）
├── engines/      数据库引擎层（EngineProtocol + 11 种实现）
├── services/     业务逻辑层（masking、audit、notify 等）
├── routers/      FastAPI 路由（每个模块独立文件）
└── tasks/        Celery 异步任务
```

## 整体进度（v1.0-GA 基线 + v2-lite 权限收敛）

| 模块 | 状态 |
|---|---|
| Sprint 0 — 项目骨架 | ✅ 完成 |
| Sprint 1 — 认证、用户、实例管理 | ✅ 完成 |
| Sprint 2 — 引擎层、在线查询、查询权限 | ✅ 完成 |
| Pack A — SQL 工单全流程 + 运维工具 | ✅ 完成 |
| Pack B — 可观测中心 + 迁移脚本 | ✅ 完成 |
| Pack C — 系统配置、审计日志、资源组、数据库注册 | ✅ 完成 |
| Pack D — 数据脱敏、数据字典、工单模板、AI Text2SQL | ✅ 完成 |
| Pack E — 多引擎补全、数据归档、SQL 回滚、通知服务 | 🔧 完成（85%）|
| Pack F — 第三方登录（LDAP/钉钉/飞书/企微/CAS） | ✅ 完成 |
| Pack G — 全链路测试、性能测试、安全扫描 | ✅ 完成 |
| Pack H — Helm Chart、CI/CD、生产环境配置 | ✅ 完成 |
| Security Hardening — 安全加固 | ✅ 完成 |
| 多级审批流 | ✅ 完成（v2-lite 首发 3 种审批人类型） |

## 最近补充

- Oracle 表 DDL 预览优先走 `DBMS_METADATA.GET_DDL('TABLE', ...)`
- DDL 接口响应新增 `copyable_ddl / raw_ddl`，前端可切换“简化 DDL / 原始 DDL”
- PostgreSQL / Oracle 数据字典列查询已补齐 `column_comment`
- PostgreSQL / Oracle 的 DDL 预览会追加 `COMMENT ON COLUMN ...`；Oracle 简化 DDL 会剥离 storage/tablespace 等物理属性，原始 DDL 保留原生输出并补充注释语句
- StarRocks 已从 MySQL 映射改为独立 `StarRocksEngine`，查询、元数据、审核、监控能力按 StarRocks 语义实现，归档首版支持 dry-run 与 purge 模式
- 会话诊断新增 `SessionSnapshot` 和 `collect_session_snapshots`，并已重做为连接/会话视角：在线会话展示完整连接清单（含空闲连接），历史会话区分平台采样快照与 Oracle ASH/AWR 活跃采样
- 会话时长字段拆分为 `connection_age_ms / state_duration_ms / active_duration_ms / transaction_age_ms`，`duration_ms/time_seconds` 仅保留为兼容字段
- TiDB 已拆为独立 `TidbEngine`，会话采集优先使用 `information_schema.CLUSTER_PROCESSLIST`
- 慢日志分析新增 `SlowQueryLog / SlowQueryConfig`，支持平台查询历史同步、原生慢日志采集、实例级阈值/周期/保留配置、SQL 指纹详情和 MySQL/PostgreSQL 执行计划分析
- 数据归档升级为审批作业：`archive_job / archive_batch_log` 记录进度和批次日志，Celery `archive` 队列执行，支持暂停、继续、取消
- Alembic 已新增 `0019_session_snapshot`、`0020_slow_query_log`、`0021_slow_query_v2`、`0022_session_collect_config`、`0023_archive_jobs`、`0024_session_duration_ms`、`0025_session_duration_fields`

## 权限实现口径（v2-lite）

后端当前以“单层单职责”为原则：

- 功能权限：`Role -> Permission`
- 实例范围：`UserGroup -> ResourceGroup -> Instance`
- 查询授权：`QueryPrivilege` 首发仅启用 `database / table`
- 审批流：首发仅启用 `users / manager / any_reviewer`

查询链路新增了权限排查接口：

```bash
POST /api/v1/query/access-check/
```

返回 `allowed / reason / layer`，用于区分是卡在身份、资源范围还是数据授权层。

资源组 / 用户组当前的后端约束：

- 资源组只负责实例范围，不再承载成员穿梭框或资源组级 Webhook 主流程
- 用户组负责成员、组长、上级组与资源组关联
- 停用资源组不能再被用户组新关联，服务层会直接拒绝请求

## 代码规范

```bash
# 格式化
ruff format .

# Lint
ruff check .

# 类型检查
mypy app/

# 运行测试
pytest tests/ -v --cov=app

# v2-lite 授权单测
./.venv/bin/python -m pytest tests/unit/test_authz_v2_lite.py

# 会话诊断与慢日志单测
./.venv/bin/python -m pytest tests/unit/test_session_diagnostic.py tests/unit/test_slowlog_service.py -q
```
