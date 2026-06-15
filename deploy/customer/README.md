# SagittaDB Enterprise v__SAGITTADB_VERSION__

SagittaDB Enterprise 是面向企业数据库治理场景的统一管控平台，帮助团队把数据库实例、SQL 变更、在线查询、查询授权、数据字典、数据脱敏、运行诊断、数据归档和审计追踪放到一套可交付、可验收、可运维的平台中。

本仓库是 SagittaDB Enterprise 的公开交付仓库，面向试用客户、实施人员和运维团队提供部署文件、安装脚本、Helm Chart、产品手册、截图示例、版本下载和供应链验收材料。后端源码、前端源码、商业构建脚本、签名私钥、License 签发工具和客户内部数据不会放在公开仓库中。

![SagittaDB Dashboard](screenshots/02-dashboard.png)

## 适合解决什么问题

SagittaDB Enterprise 适合已经有多套数据库、多个研发团队和审计要求的组织。典型场景包括：

- 统一登记 MySQL、PostgreSQL、Oracle、SQL Server、MongoDB、Redis、ClickHouse、StarRocks 等数据库实例。
- 通过 SQL 工单管理 DDL/DML 变更审批、执行和审计。
- 让研发在受控权限下自助查询数据，并自动记录查询历史。
- 统一申请、审批和回收查询权限，减少人工发账号、发密码。
- 为敏感字段配置脱敏规则，降低生产数据暴露风险。
- 查看实例运行状态、慢 SQL、容量、会话和采集异常。
- 通过数据归档处理历史数据下沉或迁移。
- 在试用、上线和验收阶段生成交付报告和脱敏诊断包。

## 界面预览

| 场景 | 截图 |
|---|---|
| 实例列表：按资源组维护数据库接入、连接状态和实例类型。 | ![实例列表](screenshots/03-instance-list.png) |
| SQL 工单：提交变更、查看风险提示并进入审批流程。 | ![SQL 工单提交](screenshots/05-workflow-submit.png) |
| 在线查询：在授权范围内选择实例、查看表结构并执行只读查询。 | ![在线查询](screenshots/08-query-workbench.png) |
| 数据字典：在平台内查看库表字段、索引和备注信息。 | ![数据字典](screenshots/10-data-dictionary.png) |
| 数据脱敏：维护敏感字段规则，保护查询和导出场景。 | ![数据脱敏](screenshots/11-masking-rule.png) |
| 商业授权：查看试用、正式授权、客户 ID 和部署指纹。 | ![License 授权](screenshots/20-license.png) |

截图来自 SagittaDB 测试环境，仅展示产品页面内容，不包含测试环境服务器 IP、浏览器地址栏或客户数据。实际页面会因版本、角色权限、License、实例数量和客户配置略有差异。

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
- [产品使用手册](docs/product-manual.md)：角色说明、登录、实例、SQL 工单、在线查询、权限、字典、脱敏、监控、归档、审计和商业交付。
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

前端健康后，使用客户侧域名或服务器入口访问 SagittaDB。不要在公开截图、工单、群聊或文档中暴露测试环境 IP、`.env`、License 文件、激活码、数据库密码或未脱敏客户数据。

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

登录后可在 `商业交付` -> `License 授权` 中完成在线激活或离线授权。也可以用脚本验证授权流程：

```bash
./verify-license.sh <activation_code> <customer_id>
```

SagittaDB Enterprise 使用统一授权中心 License-Server-Center，默认授权服务地址为 `https://license.loveai.asia`。在线激活和联网刷新会提交授权项目码 `sagittadb`，授权管理页应显示 `授权项目：SagittaDB（sagittadb）`。

在线激活前，请在授权管理页输入客户 ID，复制页面展示的“正式激活部署指纹”，交给 SagittaDB 商业支持生成激活码。HTTP 试用部署会使用兼容复制方式；HTTPS 环境优先使用浏览器剪贴板能力。

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
