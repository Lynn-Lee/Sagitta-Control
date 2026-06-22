# Sagitta Control 安装部署指南

本文面向首次部署 Sagitta Control 的客户运维、DBA 和实施人员。目标是让你在一台新服务器上按顺序完成下载、配置、启动、健康检查、首次登录、授权确认和上线前检查。

部署包只包含部署编排、脚本、Helm Chart、截图和文档；应用以固定版本容器镜像交付。请不要把服务器 IP、`.env`、License 文件、激活码、数据库密码、Token 或未脱敏客户数据发布到公开仓库、工单截图或公共群聊。

## 1. 先选部署方式

| 部署方式 | 适合场景 | 建议 |
|---|---|---|
| Docker Compose | 单机试用、POC、小规模生产、客户现场快速交付 | 首次试用优先选择，步骤最短，问题最容易定位。 |
| Kubernetes / Helm | 已有 K8s 集群、统一容器平台、生产高可用规划 | 需要客户侧提前准备 Ingress、Secret、存储、外部 PostgreSQL/Redis 和监控。 |
| 离线部署 | 服务器无法访问 GHCR 或授权服务 | 部署前先准备镜像 tar 包和离线授权材料。 |

首次部署建议先用 Docker Compose 完成业务闭环；确认功能、授权和用户流程后，再按客户生产规范迁移到 Helm。

## 2. 准备服务器

### 2.1 推荐配置

- Linux x86_64 服务器。
- Docker Engine 24 或更新版本。
- Docker Compose v2。
- `python3`、`curl`、`wget`、`unzip`。
- 4 核 CPU、8 GB 内存起步；生产建议 8 核 CPU、16 GB 内存以上。
- 100 GB 以上可用磁盘；生产按日志、备份和审计留存周期扩容。

确认基础命令：

```bash
docker --version
docker compose version
python3 --version
curl --version
```

### 2.2 网络和端口

服务器需要能访问：

- 镜像：`__IMAGE_REPOSITORY__-backend:__SAGITTA_CONTROL_VERSION__`
- 镜像：`__IMAGE_REPOSITORY__-frontend:__SAGITTA_CONTROL_VERSION__`
- 授权服务：`https://license.loveai.asia`

默认端口：

| 端口 | 用途 | 说明 |
|---|---|---|
| `80` | 前端入口 | 由 `FRONTEND_PORT` 控制，生产建议接入 HTTPS 反向代理。 |
| `8000` | 后端 API | 由 `BACKEND_PORT` 控制，通常只给内网、反向代理或运维检查访问。 |

如果服务器已有 Nginx 或其他服务占用 `80`，可以在 `.env` 中改 `FRONTEND_PORT=8080`，再由客户侧反向代理转发到该端口。

### 2.3 部署前确认清单

- 已获得 Sagitta Control 试用许可或商业授权。
- 已规划访问域名、HTTPS 证书、管理员账号、备份目录和日志留存策略。
- 已确认客户侧防火墙、安全组和反向代理允许访问前端入口。
- 已确认数据库实例接入账号只授予必要权限。
- 已确认是否接入 LDAP、CAS、OIDC、短信、钉钉、飞书或企业微信登录。
- 已确认生产升级和回滚时可以进入维护窗口。

## 3. 下载并校验部署包

在服务器上执行：

```bash
wget https://github.com/Lynn-Lee/Sagitta-Deploy/releases/download/v__SAGITTA_CONTROL_VERSION__/Sagitta-Control-v__SAGITTA_CONTROL_VERSION__.zip
wget https://github.com/Lynn-Lee/Sagitta-Deploy/releases/download/v__SAGITTA_CONTROL_VERSION__/Sagitta-Control-v__SAGITTA_CONTROL_VERSION__.zip.sha256
sha256sum -c Sagitta-Control-v__SAGITTA_CONTROL_VERSION__.zip.sha256
unzip Sagitta-Control-v__SAGITTA_CONTROL_VERSION__.zip
cd Sagitta-Control-v__SAGITTA_CONTROL_VERSION__
```

成功信号：

- `sha256sum` 输出 `OK`。
- 解压目录中能看到 `docker-compose.yml`、`.env.example`、`prepare-go-live-env.sh`、`go-live-check.sh`、`upgrade.sh`、`docs/` 和 `helm/`。

如果 `sha256sum` 失败，请重新下载 zip 和 sha256 文件，不要继续部署。

## 4. 准备 `.env`

复制示例配置：

```bash
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
```

脚本会做三件事：

- 为 `POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID` 生成强随机值。
- 将 `LICENSE_CUSTOMER_ID` 写成传入的客户 ID。
- 保留已有正式值；除非使用 `--force`，不会覆盖非占位符配置。

继续人工检查 `.env`：

| 配置项 | 必填 | 说明 |
|---|---|---|
| `POSTGRES_PASSWORD` | 是 | 内置 PostgreSQL 密码，不能是 `CHANGE_ME`。 |
| `REDIS_PASSWORD` | 是 | 内置 Redis 密码，不能是 `CHANGE_ME`。 |
| `SECRET_KEY` | 是 | 生产密钥，首次部署后不要修改；修改会影响加密数据。 |
| `LICENSE_CUSTOMER_ID` | 是 | 客户 ID，应与授权中心记录一致。 |
| `LICENSE_SERVER_URL` | 是 | 默认 `https://license.loveai.asia`。 |
| `LICENSE_DEPLOYMENT_ID` | 是 | 稳定部署 ID，升级、迁移和重启时必须保持不变。 |
| `BACKEND_PORT` | 是 | 默认 `8000`，后端健康检查使用。 |
| `FRONTEND_PORT` | 是 | 默认 `80`，前端入口使用。 |
| `ORACLE_DRIVER_MODE` / `ORACLE_CLIENT_LIB_DIR` | 按需 | 接入 Oracle 时按客户环境配置。 |

检查占位符：

```bash
grep -n 'CHANGE_ME\|^LICENSE_CUSTOMER_ID=$' .env || true
```

如果命令输出了未处理的关键配置，请先修正再启动服务。

重要：升级、迁移和重启时必须保留同一份 `.env`，尤其是 `SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID`。不要在升级时重新执行 `prepare-go-live-env.sh --force`。

## 5. Docker Compose 启动

先拉取固定版本镜像：

```bash
docker compose pull
```

启动基础服务并执行数据库迁移：

```bash
docker compose up -d postgres redis
docker compose ps postgres redis
docker compose run --rm backend alembic upgrade head
```

启动全部服务：

```bash
docker compose up -d
docker compose ps
```

成功信号：

- `postgres`、`redis`、`backend`、`celery_worker`、`celery_beat`、`frontend` 状态为 `running` 或 `healthy`。
- `docker compose run --rm backend alembic upgrade head` 正常退出，没有数据库连接或迁移错误。

如果容器反复重启，先看日志：

```bash
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 postgres
docker compose logs --tail=100 redis
```

## 6. 健康检查和访问入口

在服务器本机执行：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

如果改过端口，请替换为 `.env` 中的实际端口，例如 `BACKEND_PORT=18000`、`FRONTEND_PORT=8080` 时：

```bash
curl -fsS http://127.0.0.1:18000/health
curl -fsS http://127.0.0.1:8080/health
```

浏览器访问：

```text
http://<server>/
```

生产环境建议通过客户域名和 HTTPS 暴露服务，不建议把裸 IP 作为最终访问入口。若前端能打开但 API 失败，请优先检查 `nginx.conf`、后端容器状态和 `/api/` 反向代理。

## 7. 首次登录与授权确认

首次部署没有正式 License 时会进入 60 天全功能试用期。登录后建议先完成授权确认：

1. 使用初始化管理员账号登录 Sagitta Control。
2. 打开 `商业交付` -> `License 授权`。
3. 确认试用期、客户 ID 和部署指纹。
4. 如需正式授权，复制正式激活部署指纹。
5. 将部署指纹提供给 Sagitta Control 商业支持。
6. 获得激活码后在页面完成在线激活。
7. 激活后刷新页面，确认授权状态、有效期和授权项目正常。

`License 授权` 页面会展示客户 ID、部署指纹、授权状态和激活记录，属于客户现场敏感信息，公开文档不附该页面截图。内部验收或支持沟通时如需截图，请先遮挡公网 IP、客户 ID、部署指纹、激活码和授权状态明细。

长期离线部署可在授权页面生成 Challenge，由商业支持签发 challenge-response 文件后导入。离线授权前请先确认服务器时间准确。

## 8. 初始化业务配置

授权确认后，建议按以下顺序初始化，避免用户登录后没有资源或审批链路不完整：

1. 创建管理员、DBA、研发、审批人和审计员账号。
2. 配置角色权限。
3. 创建资源组并分配成员。
4. 接入数据库实例并测试连接。
5. 注册数据库或 Schema。
6. 配置 SQL 工单、查询权限和数据归档审批流程。
7. 配置数据脱敏规则。
8. 创建第一条 SQL 工单和一次在线查询，验证业务链路。

详细操作路径见 [产品使用手册](product-manual.md)。

## 9. 上线前检查

正式给业务团队使用前执行：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --username <admin> \
  --password '<password>'
```

若管理员启用了 2FA，请改用具备系统配置管理权限的访问令牌：

```bash
./go-live-check.sh \
  --api-base-url http://<server>:8000 \
  --frontend-url http://<server>/ \
  --token '<access_token>'
```

检查项包括：

- `.env` 关键配置不是空值或占位符。
- `APP_ENV=production`、`APP_INTEGRITY_REQUIRED=true`。
- 前后端健康接口可访问。
- 管理员认证通过。
- License 为正式授权且非试用。
- 客户 ID 与运行态一致。
- 至少存在一个活跃实例和一个活跃用户。
- 实施交付向导完成。
- 推广就绪度为 ready，且无推广前待处理项。

注意：这个脚本是正式上线门禁，不是单纯健康检查。POC 或试用阶段如果还没有正式授权、活跃实例或交付向导记录，脚本失败是预期结果；完成初始化后再重新执行。

## 10. Kubernetes / Helm 部署

部署包内包含 Helm Chart：

```bash
helm dependency update helm/sagitta-control
helm upgrade --install sagitta-control helm/sagitta-control \
  -f helm/sagitta-control/values-prod.yaml \
  --set app.secretKey='<random-secret>' \
  --set license.customerId='<customer-id>' \
  --set license.deploymentId='<stable-deployment-id>'
```

Helm 上线前请确认：

- `values-prod.yaml` 中的域名、Ingress、证书、存储类、外部 PostgreSQL 和外部 Redis 已替换为客户现场值。
- 密钥、数据库密码、License 配置和证书通过客户侧 Secret 管理系统注入，不提交到 Git。
- PostgreSQL、Redis 或外部托管服务的备份策略已经确认。
- 后端、Worker、Beat、前端 Pod 的资源限制符合客户规范。
- 日志采集、监控和告警已经接入客户平台。

Helm 部署后的健康检查仍然看前端健康入口和客户网关暴露的后端健康入口：

```bash
curl -fsS https://<domain>/health
curl -fsS https://<backend-health-url>
```

如果客户 Ingress 只通过前端 Nginx 暴露服务，`https://<domain>/health` 会反向代理到后端健康检查；如果后端 API 独立暴露，请按客户网关规则替换 `<backend-health-url>`。

## 11. 离线镜像导入

如果服务器无法访问 GHCR，请使用 Sagitta Control 支持团队提供的镜像包：

```bash
docker load < sagitta-control-backend-__SAGITTA_CONTROL_VERSION__.tar
docker load < sagitta-control-frontend-__SAGITTA_CONTROL_VERSION__.tar
docker compose up -d
```

离线部署仍需准备 License 激活材料。长期离线环境建议提前演练 challenge-response 授权流程，并把服务器时间同步方式纳入运维规范。

## 12. 常见问题

### 容器拉取失败

- 检查服务器是否能访问 GHCR。
- 确认镜像版本为 `__SAGITTA_CONTROL_VERSION__`。
- 检查代理、DNS、防火墙和客户侧镜像仓库策略。
- 离线环境请先导入镜像 tar 包，再执行 `docker compose up -d`。

### 数据库迁移失败

- 检查 `postgres` 容器是否 healthy。
- 检查 `.env` 中 `POSTGRES_PASSWORD` 是否与容器启动时一致。
- 查看 `docker compose logs --tail=100 postgres`。
- 如果已经有旧数据，请先确认是不是在错误目录或错误 Compose project 中运行迁移。

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

### 数据库实例连接失败

- 确认 Sagitta Control 服务器能访问数据库地址和端口。
- 确认数据库账号、密码和认证方式正确。
- 确认数据库账号具备必要只读视图权限。
- 如使用跳板机，检查 SSH 隧道配置和密钥格式。
