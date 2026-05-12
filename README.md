# SagittaDB 矢准数据

> 企业级多引擎数据库管控平台
> 矢向数据，精准管控

SagittaDB 是面向企业数据库治理场景的统一管控平台，覆盖数据库实例管理、SQL 工单审批上线、在线查询、数据字典、数据脱敏、SQL 洞察、运行态诊断、数据归档、审计追踪和主动通知等核心能力。平台基于 Archery v1.14.0 深度重构，当前正式版定位为 **v2.0 商业部署版 + v2-lite 授权体系**。

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
| MongoDB / Redis / ClickHouse | 已实现核心连接、查询、数据字典和监控能力；ClickHouse 已接入 SQL 活动采集，MongoDB 支持白名单写操作工单。 |
| Oracle / MSSQL / Elasticsearch / OpenSearch / Doris | 已有最小可用实现，其中 MSSQL、Elasticsearch/OpenSearch、Doris 已补齐 SQL/任务活动或基础观测兼容层；正式接入前建议先完成客户同构环境验证。 |
| Cassandra / ScyllaDB | 支持连接、Keyspace/Table/Column 元数据、表 DDL、主键/索引元数据、只读 SELECT 和基础健康/版本/集群标识；DDL/DML/BATCH 工单执行按交付边界关闭。 |

## 技术架构

| 层级 | 技术栈 |
|---|---|
| 后端 | FastAPI 0.110、SQLAlchemy 2.0 async、Alembic、Celery 5、PostgreSQL 16、Redis |
| 前端 | React 18、Vite 8、TypeScript、Ant Design 5、TanStack Query v5、Zustand |
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
| [用户使用手册](docs/user_manual.md) | 面向 DBA、研发、管理员、审计员的页面操作指南。 |
| [运维管理手册](docs/operations_guide.md) | 部署、初始化、升级、回滚、备份恢复、监控告警、故障处理和安全检查。 |

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
├── docs/                    # 产品设计、用户使用和运维管理文档
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

## 商业交付

当前版本：`v2.0 商业部署版 + v2-lite 授权体系`。
当前商业部署版本：`2.0.0`。
状态：正式版商业交付。

商业授权接入统一授权中心 `License-Server-Center`。客户部署包默认使用 `LICENSE_SERVER_URL=https://license.loveai.asia`。SagittaDB 客户端在线激活和联网刷新时会自动提交授权项目码 `sagittadb`，同时保留 `product=sagittadb` 兼容字段；授权管理页会展示 `授权项目：SagittaDB（sagittadb）`，用于现场确认当前部署正在按 SagittaDB 产品线校验授权。在线激活区域输入客户 ID 后，会预览正式激活客户 ID 和正式激活部署指纹，便于在用户授权中心生成对应激活码。

正式交付包含：

- 固定版本 Docker/Helm 公开商业部署包，不使用 `latest`。
- 商业后端镜像使用 Nuitka 编译核心 Python 模块，前端只交付 build 产物且构建阶段禁止 sourcemap。
- `.env.example`、`docker-compose.yml`、`upgrade.sh`、`verify-license.sh` 和 Nginx 配置。
- 商业 License 使用 Ed25519 签名校验；支持在线激活、联网刷新和离线 challenge-response，生产环境默认禁止旧式裸 License 导入。
- 商业镜像使用 Ed25519 签名完整性 Manifest 启动校验，镜像和客户包发布流程需完成 cosign 镜像签名与交付包签名。
- 生产环境上线前完成实例接入、审批流、权限、通知、License 在线激活/联网刷新/离线 challenge-response、备份恢复和升级回滚验证。
- 内部留存客户环境验收和 License-Server-Center 授权状态流转记录；这些记录不作为仓库长期公开文档。
- 合同条款需明确禁止逆向、篡改、绕过授权和二次分发，作为技术保护之外的法务兜底。

公开商业交付仓库方案见 [SagittaDB 公开商业交付说明](docs/public_commercial_delivery.md)。
