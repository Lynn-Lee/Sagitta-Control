# SagittaDB Enterprise 安装部署指南

本文面向首次部署 SagittaDB Enterprise 的客户运维、DBA 和实施人员。部署包只包含部署编排、脚本、Helm Chart、截图和文档，应用以固定版本容器镜像交付。

部署过程中请不要把服务器 IP、`.env`、License 文件、激活码、数据库密码或未脱敏客户数据发布到公开仓库、工单截图或公共群聊。

## 1. 部署方式选择

| 部署方式 | 适合场景 | 说明 |
|---|---|---|
| Docker Compose | 单机试用、小规模生产、POC、客户现场快速交付 | 部署步骤最简单，适合先完成试用和验收。 |
| Kubernetes / Helm | 已有 K8s 集群、统一容器平台、生产高可用规划 | 需要客户侧提供 Ingress、Secret、存储和监控规范。 |
| 离线部署 | 服务器无法访问公网镜像仓库或授权服务 | 需要提前准备镜像 tar 包和离线授权材料。 |

首次试用建议先使用 Docker Compose 完成闭环，再按客户生产规范迁移到 Helm。

## 2. 部署前准备

服务器建议配置：

- Linux x86_64 服务器。
- 4 核 CPU、8 GB 内存起步；生产环境建议 8 核 CPU、16 GB 内存以上。
- 100 GB 以上可用磁盘，生产环境按日志、备份和审计留存周期扩容。
- Docker Engine 24 或更新版本。
- Docker Compose v2。
- 可访问 `__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__` 和 `__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`。
- 可访问授权服务 `https://license.loveai.asia`；长期离线部署需提前准备离线授权流程。

部署前请确认：

- 已获得 SagittaDB Enterprise 商业授权或试用许可。
- 已规划访问域名、HTTPS 证书、管理员账号、备份目录和日志留存策略。
- 已确认数据库实例接入账号只授予必要权限。
- 已确认客户侧防火墙、反向代理和安全组允许前端入口访问。
- 已确认是否需要 LDAP、CAS、OIDC、短信、钉钉、飞书或企业微信登录。

## 3. Docker Compose 部署

解压部署包后进入目录：

```bash
cd SagittaDB-Enterprise-v__SAGITTADB_VERSION__
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
```

编辑 `.env`，至少确认：

| 配置项 | 说明 |
|---|---|
| `LICENSE_CUSTOMER_ID` | 客户 ID，应与授权中心记录一致。 |
| `LICENSE_SERVER_URL` | 授权中心地址，默认 `https://license.loveai.asia`。 |
| `SECRET_KEY` | 生产密钥，首次部署后不要随意修改。 |
| `LICENSE_DEPLOYMENT_ID` | 稳定部署 ID，重装或迁移前请备份。 |
| `BACKEND_PORT` / `FRONTEND_PORT` | 后端和前端端口。 |
| `POSTGRES_PASSWORD` / `REDIS_PASSWORD` | 数据库和缓存密码。 |
| `ORACLE_DRIVER_MODE` / `ORACLE_CLIENT_LIB_DIR` | 如需接入 Oracle，按现场环境配置。 |

启动服务：

```bash
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

浏览器访问客户侧入口：

```text
http://<server>/
```

生产环境建议通过客户域名和 HTTPS 暴露服务，不建议把裸 IP 作为最终访问入口。

## 4. 首次登录与授权

首次部署没有 License 时会进入 60 天全功能试用期。登录后建议先完成授权确认：

1. 管理员登录 SagittaDB。
2. 打开 `商业交付` -> `License 授权`。
3. 确认试用期、客户 ID 和部署指纹。
4. 如需正式授权，复制正式激活部署指纹。
5. 将部署指纹提供给 SagittaDB 商业支持。
6. 获得激活码后在页面完成在线激活。

`License 授权` 页面会展示客户 ID、部署指纹、授权状态和激活记录，属于客户现场敏感信息，公开文档不附该页面截图。内部验收或支持沟通时如需截图，请先遮挡公网 IP、客户 ID、部署指纹、激活码和授权状态明细。

长期离线部署可在授权页面生成 Challenge，由商业支持签发 challenge-response 文件后导入。

## 5. 初始化业务配置

授权确认后，建议按以下顺序初始化：

1. 创建管理员、DBA、研发、审批人和审计员账号。
2. 配置角色权限。
3. 创建资源组并分配成员。
4. 接入数据库实例并测试连接。
5. 注册数据库或 Schema。
6. 配置 SQL 工单和查询权限审批流程。
7. 创建第一条 SQL 工单和一次在线查询，验证业务链路。

可参考 [产品使用手册](product-manual.md) 中的截图和操作路径。

## 6. Kubernetes / Helm 部署

部署包内包含 Helm Chart：

```bash
helm dependency update helm/sagittadb
helm upgrade --install sagittadb helm/sagittadb \
  -f helm/sagittadb/values-prod.yaml \
  --set app.secretKey='<random-secret>' \
  --set license.customerId='<customer-id>' \
  --set license.deploymentId='<stable-deployment-id>'
```

生产环境请将密钥、数据库密码、License 配置和证书写入客户侧 Secret 管理系统，不要提交到公开仓库。Helm 上线前请确认：

- Ingress 域名和证书已经准备。
- PostgreSQL、Redis 或外部托管服务的备份策略已经确认。
- 后端、Worker、Beat、前端 Pod 的资源限制符合客户规范。
- 日志采集、监控和告警已经接入客户平台。

## 7. 上线前检查

正式给业务团队使用前执行：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --username <admin> \
  --password '<password>'
```

检查项包括：

- 服务健康。
- 生产密钥。
- 正式 License 或有效试用。
- 客户 ID 和部署指纹。
- 至少一个活跃实例。
- 交付向导。
- 验收报告。
- 推广就绪度。

若管理员启用了 2FA，请改用 `--token <access_token>`。

## 8. 离线镜像导入

如果服务器无法访问 GHCR，请使用 SagittaDB 支持团队提供的镜像包：

```bash
docker load < sagittadb-backend-__SAGITTADB_VERSION__.tar
docker load < sagittadb-frontend-__SAGITTADB_VERSION__.tar
docker compose up -d
```

离线部署仍需准备 License 激活材料。长期离线环境建议提前演练 challenge-response 授权流程。

## 9. 常见问题

### 容器拉取失败

- 检查服务器是否能访问 GHCR。
- 确认镜像版本为 `__SAGITTADB_VERSION__`。
- 检查代理、DNS、防火墙和客户侧镜像仓库策略。
- 离线环境请导入镜像 tar 包。

### 授权激活失败

- 确认服务器时间正确。
- 确认客户 ID 与授权中心记录一致。
- 确认复制的是正式激活部署指纹。
- 检查服务器是否能访问授权中心。
- 离线授权时确认 Challenge 文件和 response 文件匹配同一部署。

### 页面无法打开

- 确认 `docker compose ps` 中前端和后端服务状态正常。
- 检查 `FRONTEND_PORT`、防火墙、安全组和反向代理。
- 检查后端健康接口 `http://<server>:8000/health`。
- 检查浏览器控制台和前端容器日志。

### 数据库连接失败

- 确认 SagittaDB 服务器能访问数据库地址和端口。
- 确认数据库账号、密码和认证方式正确。
- 确认数据库账号具备必要只读视图权限。
- 如使用跳板机，检查 SSH 隧道配置和密钥格式。
