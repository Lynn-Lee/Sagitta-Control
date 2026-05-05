# SagittaDB 矢准数据

> 企业级多引擎数据库管控平台
> 矢向数据，精准管控

SagittaDB 是面向企业数据库治理场景的统一管控平台，覆盖数据库实例管理、SQL 工单审批上线、在线查询、数据字典、数据脱敏、SQL 洞察、运行态诊断、数据归档、审计追踪和主动通知等核心能力。平台基于 Archery v1.14.0 深度重构，当前正式版定位为 **v1.0-GA + v2-lite 授权体系**。

## 核心能力

| 能力 | 说明 |
|---|---|
| SQL 工单 | 支持 SQL 提交、审核、审批流快照、异步执行、执行日志和主动通知。 |
| 在线查询 | 支持多引擎查询、库/表级授权、查询历史、失败原因解释和最大返回行数治理。 |
| 数据字典 | 基于已授权查询范围查看字段、约束、索引和 DDL 预览。 |
| 权限治理 | v2-lite 权限体系，按角色权限、用户组资源范围、查询授权三层收敛访问边界。 |
| 数据安全 | 敏感字段 Fernet 加密、密码强度策略、JWT 黑名单、操作审计、数据脱敏。 |
| 运行诊断 | 支持会话管理、SQL 洞察、慢 SQL、容量监控、指标采集和诊断建议。 |
| 数据归档 | 支持归档申请、审批、分批执行、暂停、继续、取消和批次日志。 |
| 企业集成 | 支持 LDAP、钉钉、飞书、企业微信、CAS 登录，以及邮件/应用消息通知。 |

## 支持的数据库

| 类型 | 当前状态 |
|---|---|
| MySQL / TiDB / StarRocks | 已实现连接、查询、字典、会话与 SQL 活动相关能力。 |
| PostgreSQL | 已实现连接、查询、字典、慢 SQL、执行计划与容量相关能力。 |
| Oracle | 已实现连接、Schema 同步、查询与字典；Oracle 11g 需 Thick 模式。 |
| MongoDB / Redis / ClickHouse | 已实现核心连接、查询、数据字典和监控能力；ClickHouse 已接入 SQL 活动采集，MongoDB 支持白名单写操作工单。 |
| Oracle / MSSQL / Elasticsearch / OpenSearch / Doris | 已有最小可用实现，其中 MSSQL、Elasticsearch/OpenSearch、Doris 已补齐 SQL/任务活动或基础观测兼容层；正式接入前建议先完成客户同构环境验证。 |
| Cassandra | 已补齐连接、Keyspace/Table/Column 元数据、表 DDL、主键/聚簇键元数据、只读 SELECT 和基础健康指标；DDL/DML 工单执行仍关闭，正式接入前需单独立项验证。 |

## 技术架构

| 层级 | 技术栈 |
|---|---|
| 后端 | FastAPI 0.110、SQLAlchemy 2.0 async、Alembic、Celery 5、PostgreSQL 16、Redis |
| 前端 | React 18、Vite 5、TypeScript、Ant Design 5、TanStack Query v5、Zustand |
| SQL 解析 | sqlglot，支持多方言 SQL 解析、列提取和治理辅助。 |
| 异步任务 | Celery 队列：`default`、`execute`、`notify`、`archive`、`monitor`。 |
| 部署 | Docker Compose、Kubernetes + Helm、Nginx、Prometheus、Grafana。 |

```text
Browser
  -> Nginx / Frontend
  -> FastAPI API
  -> JWT + Redis 黑名单 + 权限检查
  -> Services / Engines / PostgreSQL
  -> Celery Worker / Redis / Database Engines
```

## 快速启动

本地开发和功能验证推荐使用根目录 `docker-compose.yml`。

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
```

默认访问地址：

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost |
| API 文档 | http://localhost:8000/docs，仅 `APP_ENV=development` 开启 |
| Flower | http://localhost:5555 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

首次部署后通过系统初始化接口创建管理员账号：

```bash
curl -X POST http://localhost:8000/api/v1/system/init/
```

默认管理员账号用于首次初始化。首次登录后必须按密码策略修改密码。

## 正式文档

| 文档 | 用途 |
|---|---|
| [产品设计文档](docs/sagittadb_prd.md) | 产品定位、角色、业务流程、模块设计、权限模型和商业化边界。 |
| [部署文档](docs/deploy_production_env.md) | 生产环境部署、初始化、升级、回滚和安全加固。 |
| [运维文档](docs/operations_guide.md) | 日常巡检、日志、备份恢复、监控告警、故障处理和安全检查。 |
| [用户使用手册](docs/user_manual.md) | 面向 DBA、研发、管理员、审计员的页面操作指南。 |

## 生产环境安全提示

生产部署前必须完成以下检查：

- 将 `.env` 中 `APP_ENV` 设置为 `production`。
- 替换 `SECRET_KEY`，长度不少于 32 位；生产环境严禁使用默认值。
- 替换 PostgreSQL、Redis、Grafana 等所有默认密码。
- 确认 `DATABASE_URL` 与 `DATABASE_URL_SYNC` 使用同一数据库和账号策略。
- 仅通过 HTTPS 暴露前端入口，禁止直接向公网暴露 PostgreSQL、Redis、Flower 和后端调试接口。
- 在迁移、升级和发布前执行数据库备份。
- 保持 `SECRET_KEY` 稳定；修改后会导致已加密的实例密码、SSH 密钥和敏感配置无法解密。

## 目录结构

```text
SagittaDB/
├── backend/                 # FastAPI 后端应用
│   ├── app/engines/          # 多数据库引擎适配
│   ├── app/routers/          # API 路由
│   ├── app/services/         # 业务服务
│   └── app/tasks/            # Celery 任务
├── frontend/                # React 前端应用
├── deploy/                  # 生产 Compose、Nginx、Prometheus、Grafana、Helm、备份脚本
├── docs/                    # 产品、部署、运维、用户和测试文档
├── docker-compose.yml       # 本地开发 / 功能测试 Compose
└── .env.example             # 环境变量模板
```

## 开发命令

后端：

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
alembic upgrade head
pytest tests/unit/ -v --cov=app --cov-fail-under=35
ruff format . && ruff check . && mypy app/
```

前端：

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm run build
```

## 版本状态

当前版本：`v1.0-GA + v2-lite 授权体系`。
状态：正式版商业化投放准备阶段。
建议交付方式：先在企业内网或客户测试环境完成实例接入、审批流、权限、通知和备份恢复验证，再进入生产运行。

## 最新剩余计划任务

统一任务清单见 [docs/remaining_plan.md](docs/remaining_plan.md)。当前剩余工作以发布闸门、客户同构环境验收、License Server 生产验证、交付包确认、性能基线、交付自动化和后续引擎路线为主；License 后续商业运营增强不再规划。
