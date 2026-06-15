# SagittaDB Enterprise 安装部署指南

本文面向首次部署 SagittaDB Enterprise 的客户运维、DBA 和实施人员。部署包只包含部署编排、脚本和文档，应用以固定版本容器镜像交付。

## 1. 部署前准备

服务器建议配置：

- Linux x86_64 服务器。
- 4 核 CPU、8 GB 内存起步；生产环境建议 8 核 CPU、16 GB 内存以上。
- Docker Engine 24 或更新版本。
- Docker Compose v2。
- 可访问 `__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__` 和 `__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`。
- 可访问授权服务 `https://license.loveai.asia`；长期离线部署需提前准备离线授权流程。

部署前请确认：

- 已获得 SagittaDB Enterprise 商业授权或试用许可。
- 已规划访问域名、管理员账号、备份目录和日志留存策略。
- 已确认数据库实例接入账号只授予必要权限。
- 不要把 `.env`、License 文件、激活码、部署指纹或诊断包公开到代码仓库、工单截图或公共群聊。

## 2. Docker Compose 部署

解压部署包后进入目录：

```bash
cd SagittaDB-Enterprise-v__SAGITTADB_VERSION__
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
```

然后编辑 `.env`：

- `LICENSE_CUSTOMER_ID`：客户 ID。
- `LICENSE_SERVER_URL`：授权中心地址，默认 `https://license.loveai.asia`。
- `BACKEND_PORT`、`FRONTEND_PORT`：后端和前端端口。
- `ORACLE_DRIVER_MODE`、`ORACLE_CLIENT_LIB_DIR`：如需接入 Oracle，可按现场环境配置。

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

浏览器访问：

```text
http://<server>/
```

## 3. Helm 部署

部署包内包含 Helm Chart：

```bash
helm dependency update helm/sagittadb
helm upgrade --install sagittadb helm/sagittadb \
  -f helm/sagittadb/values-prod.yaml \
  --set app.secretKey='<random-secret>' \
  --set license.customerId='<customer-id>' \
  --set license.deploymentId='<stable-deployment-id>'
```

生产环境请将密钥、数据库密码和 License 配置写入客户侧 Secret 管理系统，不要写入公开仓库。

## 4. 授权激活

首次部署没有 License 时会进入 60 天全功能试用期。正式授权流程：

1. 管理员登录 SagittaDB。
2. 打开 `商业交付` -> `License 授权`。
3. 输入客户 ID，复制页面展示的正式激活部署指纹。
4. 将部署指纹提供给 SagittaDB 商业支持。
5. 获得激活码后在页面完成在线激活。

长期离线部署可在授权页面生成 Challenge，由商业支持签发 challenge-response 文件后导入。

## 5. 上线前检查

正式给业务团队使用前执行：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --username <admin> \
  --password '<password>'
```

检查项包括生产密钥、正式 License、客户 ID、部署指纹、服务健康、交付向导、验收报告和推广就绪度。

## 6. 常见问题

容器拉取失败：

- 检查服务器是否能访问 GHCR。
- 确认镜像版本为 `__SAGITTADB_VERSION__`。
- 离线环境请使用 SagittaDB 支持团队提供的镜像包导入。

授权激活失败：

- 确认服务器时间正确。
- 确认客户 ID 与授权中心记录一致。
- 确认复制的是正式激活部署指纹。
- 检查服务器是否能访问授权中心。

页面无法打开：

- 确认 `docker compose ps` 中前端和后端服务为健康状态。
- 检查 `FRONTEND_PORT`、防火墙和反向代理。
- 检查后端健康接口 `http://<server>:8000/health`。
