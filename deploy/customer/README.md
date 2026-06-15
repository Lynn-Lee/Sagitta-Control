# SagittaDB Enterprise v__SAGITTADB_VERSION__

SagittaDB Enterprise 是面向企业数据库治理场景的统一管控平台，覆盖数据看板、数据库实例管理、SQL 工单、在线查询、查询权限、数据字典、数据脱敏、观测诊断、数据归档、系统管理、审计追踪和商业交付。

本仓库是 SagittaDB Enterprise 的公开交付仓库，面向试用客户、实施人员、DBA 和运维团队提供部署文件、安装脚本、Helm Chart、产品手册、真实测试环境页面截图、版本下载和供应链验收材料。后端源码、前端源码、商业构建脚本、签名私钥、License 签发工具和客户内部数据不会放在公开仓库中。

![SagittaDB 在线查询概览](screenshots/02-dashboard-query.png)

截图来自 SagittaDB 云 ECS 测试环境，使用页面视口截图，不包含浏览器地址栏、测试环境 IP 或登录密码。`License 授权 / 授权管理` 页面不在公开截图集中展示。

## 核心能力

- 数据看板：按查询、工单、归档、实例与库多个视角查看治理概览。
- 实例管理：统一登记数据库实例、引擎类型、连接状态和资源归属。
- SQL 工单：提交、审批、执行和审计数据库变更。
- 在线查询：在授权范围内执行受控查询，并记录查询历史。
- 查询权限：通过申请和审批控制实例、数据库或表级访问。
- 数据字典：查看库表字段、索引和结构说明。
- 数据脱敏：配置敏感字段规则，保护查询和导出场景。
- 观测中心：查看实例健康、采集状态、慢 SQL 和运行诊断。
- 数据归档：标准化归档申请、审批、执行和结果跟踪。
- 系统管理：维护用户、角色、用户组、资源组、审批流和系统配置。
- 商业交付：查看推广就绪度、交付验收、告警中心和支持材料。
- 审计日志：集中追踪登录、工单、查询、实例和配置操作。

## 页面预览

| 页面 | 截图 |
|---|---|
| 在线查询概览 | ![在线查询概览](screenshots/02-dashboard-query.png) |
| SQL 工单概览 | ![SQL 工单概览](screenshots/03-dashboard-workflow.png) |
| 数据归档概览 | ![数据归档概览](screenshots/04-dashboard-archive.png) |
| 实例与库概览 | ![实例与库概览](screenshots/05-dashboard-instance.png) |
| 工单列表 | ![工单列表](screenshots/06-workflow-list.png) |
| 提交工单 | ![提交工单](screenshots/07-workflow-submit.png) |
| 工单模板 | ![工单模板](screenshots/08-workflow-templates.png) |
| 执行查询 | ![执行查询](screenshots/09-query-workbench.png) |
| 查询权限 | ![查询权限](screenshots/10-query-privileges.png) |
| 查询历史 | ![查询历史](screenshots/11-query-history.png) |
| 观测中心 | ![观测中心](screenshots/12-monitor.png) |
| 数据归档 | ![数据归档](screenshots/13-archive.png) |
| 数据字典 | ![数据字典](screenshots/14-data-dictionary.png) |
| 实例管理 | ![实例管理](screenshots/15-instance-management.png) |
| 用户管理 | ![用户管理](screenshots/16-user-management.png) |
| 资源组管理 | ![资源组管理](screenshots/17-resource-groups.png) |
| 角色管理 | ![角色管理](screenshots/18-role-management.png) |
| 用户组管理 | ![用户组管理](screenshots/19-user-groups.png) |
| 审批流管理 | ![审批流管理](screenshots/20-approval-flows.png) |
| 系统配置 | ![系统配置](screenshots/21-system-config.png) |
| 数据脱敏规则 | ![数据脱敏规则](screenshots/22-masking-rules.png) |
| 交付与支持 | ![交付与支持](screenshots/23-commercial-support.png) |
| 审计日志 | ![审计日志](screenshots/24-audit-log.png) |

## 当前版本与镜像

- 产品版本：`__SAGITTADB_VERSION__`
- 后端镜像：`__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- 前端镜像：`__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`
- 镜像标签：固定版本标签，不使用 `latest`
- 试用策略：首次部署进入 60 天全功能试用期
- 在线授权：默认至少每 7 天成功联网刷新一次

长期离线部署请提前联系 SagittaDB 商业支持，使用 challenge-response 离线授权流程。

## 文档入口

- [安装部署指南](docs/installation.md)：服务器准备、Docker Compose 部署、Helm 部署、授权激活和上线检查。
- [运维升级指南](docs/operations-upgrade.md)：日常巡检、备份、升级、回滚、日志诊断和安全基线。
- [产品使用手册](docs/product-manual.md)：按真实菜单顺序说明各功能页面和常用流程。
- [法律提示](LEGAL-NOTICE.md)：授权、知识产权、免责声明和使用边界。

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
# 按现场信息确认 .env 中的授权、域名、端口、密钥和通知配置。
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

前端健康后，使用客户侧域名或服务器入口访问 SagittaDB。公开截图、工单、群聊和文档中不要暴露测试环境 IP、`.env`、License 文件、激活码、数据库密码或未脱敏客户数据。

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

生产环境请将密钥、数据库密码、License 配置和证书交给客户侧 Secret 管理系统，不要写入公开仓库。

## 上线门禁

正式给业务团队使用前，建议执行：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --username <admin> \
  --password '<password>'
```

门禁会检查生产密钥、正式 License、客户 ID、部署指纹、服务健康、交付向导、验收报告和推广就绪度。若管理员启用了 2FA，请改用 `--token <access_token>`。

## 升级入口

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

升级脚本会拉取固定版本镜像、备份 PostgreSQL、执行 Alembic 迁移、重启服务并检查前后端健康状态。升级前请阅读 [运维升级指南](docs/operations-upgrade.md)，并确认已经完成数据库备份。

## License 与试用

登录后可在 `商业交付` -> `License 授权` 中完成在线激活或离线授权。该页面包含客户 ID、部署指纹、激活状态等敏感信息，因此公开 README 和产品手册不提供该页面截图。

也可以用脚本验证授权流程：

```bash
./verify-license.sh <activation_code> <customer_id>
```

SagittaDB Enterprise 使用统一授权中心 License-Server-Center，默认授权服务地址为 `https://license.loveai.asia`。在线激活和联网刷新会提交授权项目码 `sagittadb`。

## 供应链材料

每个 Release 提供：

- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip`
- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256`
- `SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sig.json`
- 后端镜像 CycloneDX SBOM、sha256 和签名 bundle
- 前端镜像 CycloneDX SBOM、sha256 和签名 bundle

客户侧可以先校验 sha256，再按内部供应链流程归档 SBOM 和签名材料。

## 安全边界

公开仓库和部署包不包含 SagittaDB 源码、签发工具、私钥、真实客户 License、真实激活码、客户数据库连接信息或内部验收记录。共享日志、截图和诊断包前，请先完成脱敏处理。
