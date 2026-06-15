# SagittaDB 矢准数据

> 企业级多引擎数据库管控平台
> 矢向数据，精准管控

SagittaDB 是面向企业数据库治理场景的统一管控平台，覆盖数据库实例管理、SQL 工单审批上线、在线查询、数据字典、数据脱敏、SQL 洞察、运行态诊断、数据归档、审计追踪和主动通知等核心能力。平台基于 Archery v1.14.0 深度重构，当前正式版定位为 **v2.2 商业部署版 + v2-lite 授权体系**。

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

登录后可点击右上角用户名进入个人菜单：`个人设置` 用于维护显示名称、邮箱和二步验证（2FA），`修改密码` 为独立弹窗，仅处理当前账号密码更新。

## 正式文档

| 文档 | 用途 |
|---|---|
| [正式商业推广文案](docs/commercial_promotion_copy.md) | 面向官网、销售、试用邀请和商业推广材料的产品价值与宣传口径。 |
| [商业版产品使用手册](docs/commercial_product_manual.md) | 面向试用客户和培训场景的正式用户操作指南。 |
| [商业版运维部署维护升级文档](docs/commercial_ops_deployment_guide.md) | 面向客户运维、实施和 DevOps 的部署、授权、巡检、备份、升级和回滚指南。 |
| [产品设计文档](docs/sagittadb_prd.md) | 产品定位、角色、业务流程、模块设计、权限模型和商业化边界。 |
| [用户使用手册](docs/user_manual.md) | 面向 DBA、研发、管理员、审计员的页面操作指南。 |
| [运维管理手册](docs/operations_guide.md) | 部署、初始化、升级、回滚、备份恢复、监控告警、故障处理和安全检查。 |

## 内部源码发布

内部 ECS 测试环境和可访问私有仓库的自管环境，统一使用服务器端 SSH deploy key 直接拉取 Git 并部署：

```bash
cd /opt/sagittadb/source
COMPOSE_PROJECT_NAME=sagittadb-source-test bash deploy/update-prod.sh --ref origin/main
```

`deploy/update-prod.sh` 会校验 SSH Git remote、拉取目标版本，并按变更范围自动选择备份、迁移、镜像构建和服务重建；后端、Worker、Beat、Flower 共用同一个后端镜像，普通文档或 CI 改动会跳过镜像构建。首次配置 deploy key、remote、回滚和发布后验证步骤见 [运维管理手册](docs/operations_guide.md#24-内部-ecs-源码直拉部署约定)。

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
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.lock
uv pip install --no-deps -e .
uvicorn app.main:app --reload --port 8000
alembic upgrade head
pytest tests/unit/ -v --cov=app --cov-fail-under=35
ruff format . && ruff check .
while IFS= read -r target; do
  mypy --follow-imports=silent "$target"
done < mypy-baseline.txt
```

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
npm run build
```

## 商业交付

当前版本：`v2.2 商业部署版 + v2-lite 授权体系`。
当前商业部署版本：`2.2.0`。
状态：正式版商业交付。

v2.1 重点增强 Oracle 引擎观测能力：会话监控优先使用 RAC 友好的 `GV$SESSION/GV$PROCESS/GV$SQL` 组合，SQL 洞察新增 Oracle SQL Monitor、AWR SQLStat、Cursor Cache 和当前会话 SQL 降级链路，并补充等待事件、阻塞会话、长事务和长操作摘要。所有 Oracle 诊断采集均使用 `python-oracledb` 参数化只读查询；权限不足时返回 warning 并自动降级，不执行 kill、dump、baseline、profile、patch 等高风险诊断动作。

v2.1.3 重点打磨前端操作体验：统一系统管理、观测中心、查询、归档、工单等页面的操作按钮、搜索入口、导入导出和弹窗确认按钮样式；常规按钮统一为 36px 高和图标 + 文字结构，并按主操作、查看/管理/刷新、编辑、导入导出、中性操作、危险操作规划语义色；登录页第三方接入入口改为纯图标按钮并通过悬停提示说明“使用 XXX 登录”，LDAP/CAS/OIDC 保持大写，钉钉、飞书、企业微信使用中文展示名，企业入口点击后的未启用/未配置提示与 DataFusionX-Enterprise 对齐，例如 `飞书登录未启用或 App ID 未配置。`、`CAS 登录未启用或服务器地址未配置。`、`OIDC 登录未启用或 Client ID / Issuer 未配置。`，LDAP 登录模式使用更紧凑一致的返回图标和认证标题块，并与账号密码登录表单保持一致的输入框和按钮字号；补充多处图标按钮文案与危险操作视觉层级，并优化全局按钮/弹窗/表格工具区细节，让客户生产环境的管理界面更一致、更易扫描。

商业推广前 UI 颜色审核已完成收口：登录页从偏靛紫氛围统一回 SagittaDB 品牌蓝与深炭黑主轴；后台主界面保留 `#165DFF` 企业蓝、`#0F172A` 深色顶栏、`#F2F3F5` 中性页面底色和白色内容卡片；Dashboard、慢 SQL、监控趋势等图表色板收敛到统一品牌/功能色，在线查询、数据字典、工单模板、用户导入和用户组导入等页面清理默认 Ant Design 蓝色残留；资源组数据库类型标签对亮黄色场景做对比度修正，避免客户演示和投影环境下文字发虚。

商业控制台 UI 已按 v2.2 交付标准继续收口：全局 PageHeader、FilterCard、SectionCard、TableEmptyState 和 SectionLoading 统一页面标题说明、筛选区、表格外壳、空态和加载态；Dashboard 四类概览页统一指标卡、图表卡、时间范围选择器、Tooltip、Legend 和空图提示；实例管理、SQL 工单、查询历史和审计日志等高频列表页统一为“业务说明 + 筛选卡 + 表格卡”结构，移动端动作区自动铺满，筛选无结果、未配置和无权限等状态不再混用同一句空文案。

前端中文化最终口径已收口到全局入口：Ant Design 日期选择器和日期范围选择器统一使用简体中文 locale，月份、星期、`Today`、`Select date`、`Start date`、`End date` 等默认文案分别显示为 `今天`、`请选择日期`、`开始日期`、`结束日期` 等中文文案。若生产环境仍出现英文日期控件，按旧前端静态资源或浏览器缓存未刷新处理，应重新构建发布前端并清理 Nginx/CDN/浏览器缓存。

v2.2.0 已完成商业发布链路补强：客户部署包、sha256、Ed25519 客户包签名、前后端 CycloneDX SBOM、SBOM sha256 和 cosign bundle 均已生成；后端 Nuitka 商业镜像和前端生产镜像已完成真实构建、GHCR 推送、cosign 镜像签名、SBOM attestation 和反向验签。商业发布 workflow 已接入 `scripts/validate-commercial-release-materials.sh`，发布侧会校验客户包、签名、SBOM 与 bundle 材料；产品内 `CommercialOpsService.delivery_preflight()` 会把备份恢复脚本、升级回滚脚本、商业构建门禁脚本、客户包 sha256、客户包签名和 SBOM 材料纳入推广就绪度，当前本地 2.2.0 交付预检结果为 `ready`。容器运行态会随后端带入 `commercial_delivery_manifest.json`，在看不到宿主机交付目录时使用已验证发布清单兜底，避免商业页把材料文件布局误判为交付阻塞。

系统配置页继续对齐 DataFusionX-Enterprise 的接入方式视觉：钉钉、飞书、企微测试发送按钮使用发送图标，CAS/OIDC 增加与 LDAP 同样样式的连通性测试，CAS/OIDC 图标分别使用全局网络和 Key 图标。

商业授权接入统一授权中心 `License-Server-Center`。源码部署模板和客户部署包默认使用 `LICENSE_SERVER_URL=https://license.loveai.asia`，并预置官方 License 验签公钥。SagittaDB 客户端在线激活和联网刷新时会自动提交授权项目码 `sagittadb`，同时保留 `product=sagittadb` 兼容字段；授权管理页会展示 `授权项目：SagittaDB（sagittadb）`，用于现场确认当前部署正在按 SagittaDB 产品线校验授权。在线激活区域输入客户 ID 后，会预览正式激活客户 ID 和正式激活部署指纹，便于在用户授权中心生成对应激活码；复制按钮兼容 HTTPS 和 HTTP 试用部署，HTTP 环境会自动使用降级复制方式。

商业交付闭环已内置到产品：管理员可在 `商业交付` → `交付与支持` 页面完成实施交付向导、生成 Markdown/JSON 验收报告、导出脱敏诊断包、查看合规报表、处理告警事件和确认引擎支持矩阵。在线激活和联网刷新会向授权中心上报 usage/runtime 摘要，便于客户成功、续费和支持排障。

商业试用初始化已内置到交付页：管理员可点击 `初始化试用环境`，幂等创建商业试用资源组、用户组、标准审批流和样例审计记录；若现场已有活跃数据库实例，会进一步生成 SQL 工单、查询权限申请、在线查询、归档作业和监控快照演示数据，并自动生成一次验收报告。该流程不会伪造活跃实例或保存真实数据库密码，未接入实例时会保留“首个实例”待处理项。

客户包新增正式推广前硬门禁：`prepare-go-live-env.sh` 会为客户现场生成生产随机密钥和稳定部署 ID，`go-live-check.sh` 会严格校验生产环境变量、正式 License、客户 ID、部署指纹、活跃实例、实施向导、验收报告、运行健康和推广就绪度。该脚本通过后，才视为客户现场具备正式推广上线条件；任一失败项都应先完成配置或补验收。

发布机制与 DataFusionX 对齐：源码 `main` 分支只触发快速 CI 和版本记录，不自动发布商业包；推送 `release/**` 分支生成 RC 候选商业镜像和部署包，但不默认同步公开交付仓库；推送正式 `vX.Y.Z` 标签生成最终商业交付包并同步到 `Lynn-Lee/SagittaDB-Enterprise`，并创建或更新对应 GitHub Release。手动触发商业发布时默认只生成临时包，只有显式勾选发布才同步公开发布仓库。

正式交付包含：

- 固定版本 Docker/Helm 公开商业部署包，不使用 `latest`。
- 商业后端镜像使用 Nuitka 编译核心 Python 模块，前端只交付 build 产物且构建阶段禁止 sourcemap。
- `.env.example`、`docker-compose.yml`、`upgrade.sh`、`verify-license.sh` 和 Nginx 配置。
- 商业 License 使用 Ed25519 签名校验；支持在线激活、联网刷新和离线 challenge-response，生产环境默认禁止旧式裸 License 导入。
- 商业镜像使用 Ed25519 签名完整性 Manifest 启动校验，镜像和客户包发布流程需完成 cosign 镜像签名与交付包签名。
- 生产环境上线前完成实例接入、审批流、权限、通知、License 在线激活/联网刷新/离线 challenge-response、备份恢复和升级回滚验证。
- 内部留存客户环境验收和 License-Server-Center 授权状态流转记录；公开仓库和
  Release 说明不得包含真实客户 ID、域名、License、token、部署指纹、内部验收
  记录或客户现场截图。
- 合同条款需明确禁止逆向、篡改、绕过授权和二次分发，作为技术保护之外的法务兜底。

公开商业交付仓库方案见 [SagittaDB 公开商业交付说明](docs/public_commercial_delivery.md)。
