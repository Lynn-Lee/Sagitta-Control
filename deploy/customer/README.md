# SagittaDB Enterprise v__SAGITTADB_VERSION__

SagittaDB Enterprise 是面向企业数据库治理场景的一体化管控平台，帮助企业把数据库实例、SQL 变更、在线查询、权限申请、数据字典、数据脱敏、运行观测、数据归档和审计日志统一到一个可审批、可追踪、可运营的工作台中。

平台适合 DBA、研发团队、运维团队、数据安全负责人和审计人员共同使用：管理员接入数据库并配置组织权限，研发在授权范围内提交工单或执行查询，DBA 与审批人完成审核和执行，审计人员通过日志与看板追踪关键操作。

## 核心功能

- 数据看板：汇总查询、工单、归档、实例与库等关键指标，帮助团队快速掌握治理状态。
- SQL 工单：支持 SQL 变更提交、风险识别、审批流转、执行记录和结果审计。
- 在线查询：提供受控 SQL 查询工作台，结合查询权限、行数限制、脱敏规则和查询历史使用。
- 观测中心：集中查看实例健康、采集状态、性能指标、SQL 洞察、会话洞察和采集诊断。
- 数据字典：展示实例、库、表、字段、索引和约束信息，降低直接登录数据库查看结构的需求。
- 实例管理：统一维护数据库连接、引擎类型、默认库、状态、资源组和连通性。
- 权限治理：通过用户、角色、用户组、资源组和审批流控制菜单、实例、库表和流程权限。
- 数据脱敏：按字段名、库表范围和脱敏类型配置规则，保护在线查询和导出场景中的敏感数据。
- 数据归档：标准化归档申请、影响评估、审批、执行和任务记录，支撑历史数据治理。
- 审计日志：记录账号、工单、查询、实例、系统配置和授权相关操作，便于合规追溯。

## 功能预览

### 数据看板

![数据看板](screenshots/02-dashboard-query.png)

### SQL 工单

![SQL 工单](screenshots/06-workflow-list.png)

### 在线查询

![在线查询](screenshots/09-query-workbench.png)

### 观测中心

![观测中心](screenshots/12-monitor.png)

### 数据字典

![数据字典](screenshots/14-data-dictionary.png)

## 当前版本

- 产品版本：`__SAGITTADB_VERSION__`
- 后端镜像：`__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- 前端镜像：`__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`
- 镜像标签：固定版本标签，不使用 `latest`

SagittaDB 支持试用和正式授权，部署完成后可在产品内完成激活或续期。

## 文档入口

- [安装部署指南](docs/installation.md)：服务器准备、Docker Compose 部署、Helm 部署、授权激活和上线检查。
- [产品使用手册](docs/product-manual.md)：从部署后的初始化配置到各模块日常使用的完整说明。
- [运维升级指南](docs/operations-upgrade.md)：日常巡检、备份、升级、回滚、日志诊断和安全基线。
- [使用授权](LEGAL-NOTICE.md)：试用、学习、内部验证和继续使用授权说明。

## 快速部署

从 GitHub Releases 下载完整部署包：

```bash
wget https://github.com/Lynn-Lee/SagittaDB-Enterprise/releases/download/v__SAGITTADB_VERSION__/SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip
wget https://github.com/Lynn-Lee/SagittaDB-Enterprise/releases/download/v__SAGITTADB_VERSION__/SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256
sha256sum -c SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256
unzip SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip
cd SagittaDB-Enterprise-v__SAGITTADB_VERSION__
```

准备环境并启动：

```bash
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
# 按现场信息确认 .env 中的域名、端口、密钥、授权和通知配置。
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

前端健康后，使用客户侧域名或服务器入口访问 SagittaDB。

## Kubernetes / Helm

仓库内包含 Helm Chart：

```bash
helm dependency update helm/sagittadb
helm upgrade --install sagittadb helm/sagittadb \
  -f helm/sagittadb/values-prod.yaml \
  --set app.secretKey='<random-secret>' \
  --set license.customerId='<customer-id>' \
  --set license.deploymentId='<stable-deployment-id>'
```

生产环境请将密钥、数据库密码、License 配置和证书交给客户侧 Secret 管理系统。

## 上线检查

正式给业务团队使用前，建议执行：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --username <admin> \
  --password '<password>'
```

上线检查会验证服务健康、管理员登录、关键配置、授权状态、交付向导和基础功能可用性。若管理员启用了 2FA，请改用 `--token <access_token>`。

## 升级入口

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

升级脚本会拉取固定版本镜像、备份 PostgreSQL、执行 Alembic 迁移、重启服务并检查前后端健康状态。升级前请阅读 [运维升级指南](docs/operations-upgrade.md)，并确认已经完成数据库备份。

## 供应链材料

每个 Release 提供：

- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip`
- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256`
- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sig.json`
- 后端镜像 CycloneDX SBOM、sha256 和签名 bundle
- 前端镜像 CycloneDX SBOM、sha256 和签名 bundle

客户侧可以先校验 sha256，再按内部供应链流程归档 SBOM 和签名材料。

## 安全提示

公开仓库和部署包不包含 SagittaDB 源码、签发工具、私钥、真实客户 License、真实激活码、客户数据库连接信息或内部验收记录。共享日志、截图和诊断包前，请先完成脱敏处理。
