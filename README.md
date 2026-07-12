# Sagitta Control 矢准数据库安全管控平台

Sagitta Control 是面向企业数据库安全管控场景的独立平台，覆盖数据库实例管理、SQL 工单审批上线、在线查询、数据字典、数据脱敏、SQL 洞察、运行态诊断、数据归档、审计追踪和主动通知等核心能力。当前正式版定位为 **v3.0.0 用户部署版 + v2-lite 授权体系**。

## 核心能力

| 能力 | 说明 |
|---|---|
| SQL 工单 | 支持 SQL 提交、审核、审批流快照、异步执行、执行日志和主动通知。 |
| 在线查询 | 支持多引擎查询、库/表级授权、查询历史、失败原因解释和最大返回行数治理。 |
| 数据字典 | 基于已授权查询范围查看字段、约束、索引和 DDL 预览。 |
| 权限治理 | v2-lite 权限体系，按角色权限、用户组资源范围、查询授权三层收敛访问边界。 |
| 数据安全 | 敏感字段 Fernet 加密、密码强度策略、个人资料维护、独立改密入口、2FA、JWT 黑名单、操作审计、数据脱敏。 |
| 运行诊断 | 支持会话管理、SQL 洞察、当前慢查询/锁等待风险、容量监控、指标采集和诊断建议。 |
| 数据归档 | 支持归档申请、审批、分批执行、暂停、继续、取消和批次日志。 |
| 主动通知 | 审批提交、流转、完成、驳回和取消会写入站内通知，并通过企业自建应用精准推送钉钉、飞书或企业微信；邮件作为外部失败或未配置时的兜底通道。 |
| 企业集成 | 支持 LDAP、OIDC、钉钉、飞书、企业微信、CAS 登录，以及邮件/应用消息通知。 |

## 支持的数据库

| 类型 | 当前状态 |
|---|---|
| MySQL / TiDB / StarRocks | 已实现连接、查询、字典、会话与 SQL 活动相关能力。 |
| PostgreSQL | 以实例类型 `pgsql` 接入，已实现连接、查询、字典、慢 SQL、执行计划与容量相关能力。 |
| MongoDB / Redis / ClickHouse | 已实现核心连接、查询、数据字典和监控能力；ClickHouse 已接入 SQL 活动采集，MongoDB 支持白名单写操作工单。 |
| Oracle / MSSQL / Elasticsearch / OpenSearch / Doris | 已有最小可用实现，其中 MSSQL、Elasticsearch、OpenSearch、Doris 已补齐 SQL/任务活动或基础观测兼容层；Elasticsearch 与 OpenSearch 使用独立引擎入口和客户端；正式接入前必须完成客户同构环境验证。 |
| Cassandra / ScyllaDB | 只读/元数据边界支持，覆盖连接、Keyspace/Table/Column 元数据、表 DDL、主键/索引元数据、只读 SELECT、基础健康、peer、容量估算和 compaction 历史；DDL/DML/BATCH 工单执行按交付边界关闭，读写延迟、tombstone、SSTable、cache、thread pool 等深度指标需 JMX/sidecar。 |

## 技术架构

| 层级 | 技术栈 |
|---|---|
| 后端 | FastAPI 0.138、SQLAlchemy 2.0 async、Alembic、Celery 5、PostgreSQL 16、Redis |
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

登录后可点击右上角用户名进入个人菜单：`个人设置` 用于维护显示名称、邮箱和二步验证（2FA），`修改密码` 为独立弹窗，仅处理当前账号密码更新。

## 正式文档

| 文档 | 用途 |
|---|---|
| [README](README.md) | 项目入口、快速启动、研发命令和发布说明。 |
| [产品设计文档](docs/sagitta_control_prd.md) | 产品定位、角色、业务流程、模块设计、权限模型和产品化边界。 |
| [用户使用手册](docs/user_manual.md) | 面向 DBA、研发、管理员、审计员的页面操作指南。 |
| [安装部署手册](docs/installation_deployment.md) | 首次部署、服务器准备、Docker Compose / Helm 部署、授权激活和上线检查。 |
| [运维升级手册](docs/operations_upgrade.md) | 日常巡检、备份、升级、回滚、日志诊断和安全基线。 |

源码仓库只保留以上长期维护文档；历史计划、一次性验证报告、阶段性测试记录、发布模板和已完成优化手册不再作为正式文档维护。用户部署仓库文档由这些标准文档和 `deploy/customer/` 下的部署脚本生成。

## 内部源码发布

内部 ECS 测试环境和可访问私有仓库的自管环境，统一使用服务器端 SSH deploy key 直接拉取 Git 并部署：

```bash
cd /opt/sagitta-control/source
COMPOSE_PROJECT_NAME=sagitta-control-source-test bash deploy/update-prod.sh --ref origin/main
```

`deploy/update-prod.sh` 会校验 SSH Git remote、拉取目标版本，并按变更范围自动选择备份、迁移、镜像构建和服务重建；后端、Worker、Beat、Flower 共用同一个后端镜像，普通文档或 CI 改动会跳过镜像构建。首次部署、回滚和发布后验证步骤见 [安装部署手册](docs/installation_deployment.md) 与 [运维升级手册](docs/operations_upgrade.md)。

## 生产环境安全提示

生产部署前必须完成以下检查：

- 将 `.env` 中 `APP_ENV` 设置为 `production`。
- 替换 `SECRET_KEY`，长度不少于 32 位；生产环境严禁使用默认值。
- 将 `CORS_ORIGINS` 配置为可信前端域名列表；生产环境禁止使用通配符 `*`。
- 公网 HTTPS 生产环境必须设置 `AUTH_COOKIE_SECURE=true` 且保持 `ALLOW_INSECURE_AUTH_COOKIE=false`；仅 HTTP 源码测试环境可显式设置 `ALLOW_INSECURE_AUTH_COOKIE=true` 作为临时豁免。
- 替换 PostgreSQL、Redis、Grafana 等所有默认密码。
- 确认 `DATABASE_URL` 与 `DATABASE_URL_SYNC` 使用同一数据库和账号策略。
- 仅通过 HTTPS 暴露前端入口，禁止直接向公网暴露 PostgreSQL、Redis、Flower 和后端调试接口。
- 前端 Nginx 必须保留生产 CSP 响应头，限制脚本来源、禁止被第三方 frame 嵌入；浏览器登录态由 HttpOnly Cookie 承载，并通过 `X-CSRF-Token` 做写操作 CSRF 校验。
- 在迁移、升级和发布前执行数据库备份。
- 保持 `SECRET_KEY` 稳定；修改后会导致已加密的实例密码、SSH 密钥和敏感配置无法解密。

## 目录结构

```text
Sagitta Control/
├── backend/                 # FastAPI 后端应用
│   ├── app/engines/          # 多数据库引擎适配
│   ├── app/routers/          # API 路由
│   ├── app/services/         # 业务服务
│   └── app/tasks/            # Celery 任务
├── frontend/                # React 前端应用
├── deploy/                  # 生产 Compose、Nginx、Prometheus、Grafana、Helm、备份脚本
├── docs/                    # 产品设计、使用、安装部署和运维升级文档
├── docker-compose.yml       # 本地开发 / 功能测试 Compose
└── .env.example             # 环境变量模板
```

## 开发命令

后端：

```bash
cd backend
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.lock
uv pip install --no-deps -e .
uvicorn app.main:app --reload --port 8000
alembic upgrade head
pytest tests/unit/ -v --cov=app --cov-fail-under=58
ruff format . && ruff check .
mypy app
uvx pip-audit --disable-pip --no-deps -r requirements.lock
```

后端 CI 以全量 `mypy app`（`strict = true`）作为硬门禁——`app/` 下 134 个源文件全部零类型错误，新增代码必须保持 strict 清洁。单测覆盖率门槛当前为 58%，后续按模块补测后继续提升关键服务覆盖率。仓库转为 public 后，GitHub Actions 统一使用 GitHub-hosted 默认 runner（`runs-on: ubuntu-latest`），CI 中显式安装 Node.js 22、Python 3.12 和 uv，不再依赖旧 self-hosted runner 预装环境。

修改 `backend/pyproject.toml` 的依赖后，必须刷新并提交后端锁文件：

```bash
uv pip compile --python-version 3.12 --universal --extra dev \
  --custom-compile-command 'uv pip compile --python-version 3.12 --universal --extra dev --output-file backend/requirements.lock backend/pyproject.toml' \
  --output-file backend/requirements.lock backend/pyproject.toml
```

前端：

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm audit --audit-level=high
npm run build
```

## 交付支持

当前源码版本对应用户部署版本 `3.0.0`。Sagitta Control 的用户部署包由本源码仓库的发布流程生成，并同步到 [Lynn-Lee/Sagitta-Deploy](https://github.com/Lynn-Lee/Sagitta-Deploy) 公开部署仓库。

用户部署包含固定版本 Docker/Helm 部署包、License 授权、客户包签名、SBOM、上线验收、升级回滚和运维文档。源码 `main` 分支只触发源码 CI 和版本记录；`release/**` 分支生成 RC 候选包；正式 `vX.Y.Z` 标签或显式手动发布才同步公开部署仓库。CI 与用户部署发布 workflow 均使用 `ubuntu-latest` GitHub-hosted runner；用户部署包默认不上传为 Actions artifact，避免大包占用制品存储配额。

客户安装、升级和使用入口见 [Sagitta-Deploy](https://github.com/Lynn-Lee/Sagitta-Deploy)，源码仓库内以 [安装部署手册](docs/installation_deployment.md)、[产品使用手册](docs/user_manual.md) 和 [运维升级手册](docs/operations_upgrade.md) 为准。
