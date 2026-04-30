# SagittaDB 生产部署文档

> 文档版本：v1.0
> 适用版本：SagittaDB v1.0-GA + v2-lite 授权体系
> 目标读者：实施工程师、DevOps、系统管理员、运维工程师

## 1. 部署目标

本文档说明如何将 SagittaDB 部署为正式生产环境。部署文档只覆盖“如何上线”，长期巡检、备份恢复、故障处理和安全检查请参考 [运维文档](operations_guide.md)。

SagittaDB 支持两种生产部署模式：

| 模式 | 适用场景 | 推荐程度 |
|---|---|---|
| Docker Compose 生产模式 | 单机、企业内网、中小团队、PoC 转生产。 | 推荐作为首选交付方式。 |
| Kubernetes + Helm | 多节点、高可用、云原生平台、统一集群管理。 | 适合已有 K8s 能力的企业。 |

## 2. 部署架构

```text
User Browser
  -> HTTPS / Nginx
  -> Frontend
  -> Backend API
  -> PostgreSQL / Redis
  -> Celery Worker
  -> Database Engines
```

核心服务：

| 服务 | 说明 |
|---|---|
| `frontend` | 前端静态资源服务和 API 反向代理。 |
| `backend` | FastAPI 后端 API。 |
| `celery_worker` | 异步执行 SQL、通知、归档和采集任务。 |
| `celery_beat` | 定时任务调度。 |
| `postgres` | 平台元数据数据库。 |
| `redis` | Celery broker、Token 黑名单和临时缓存。 |
| `flower` | Celery 任务监控。 |
| `prometheus` / `grafana` / `alertmanager` | 可选外围监控组件。 |

## 3. 服务器要求

### 3.1 Docker Compose 模式

| 资源 | 最低配置 | 推荐配置 |
|---|---|---|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 系统盘 | 50 GB SSD | 100 GB SSD |
| 数据盘 | 100 GB | 500 GB 以上，独立挂载 |
| 操作系统 | Ubuntu 22.04 LTS / Rocky Linux 9 | Ubuntu 22.04 LTS |
| 网络 | 企业内网可达目标数据库 | HTTPS 域名 + 内网数据库网络 |

### 3.2 Kubernetes 模式

| 资源 | 建议 |
|---|---|
| Kubernetes | 1.25+ |
| 节点 | 至少 3 个工作节点 |
| 存储 | 支持动态 PVC 的持久化存储 |
| Ingress | Nginx Ingress / Traefik / 企业标准网关 |
| Secret 管理 | Kubernetes Secret 或企业密钥管理系统 |

## 4. 生产环境安全要求

上线前必须完成以下安全配置：

- `APP_ENV=production`。
- `DEBUG=false`。
- `SECRET_KEY` 替换为 32 位以上随机字符串。
- `POSTGRES_PASSWORD` 和 `REDIS_PASSWORD` 替换为强密码。
- `DATABASE_URL` 与 `DATABASE_URL_SYNC` 使用生产数据库账号和密码。
- 对外只暴露 HTTPS 入口，不向公网暴露 PostgreSQL、Redis、Flower、Prometheus、Grafana 管理口。
- 生产环境默认不开放 `/docs`，如需访问仅允许内网临时开放。
- 首次初始化后立即修改默认管理员密码。
- 升级、迁移和发布前必须执行数据库备份。
- 不得随意修改 `SECRET_KEY`，否则已加密数据无法解密。

生成密钥示例：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 5. Docker Compose 生产部署

### 5.1 安装 Docker

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 5.2 准备目录

```bash
sudo mkdir -p /data/sagittadb/{postgres,redis,prometheus,grafana,downloads,backups}
sudo chown -R $USER:$USER /data/sagittadb
```

### 5.3 获取代码

```bash
cd /opt
git clone https://github.com/Lynn-Lee/SagittaDB.git
cd SagittaDB
```

私有交付场景可替换为企业内部 Git 地址或离线代码包。

### 5.4 配置环境变量

```bash
cp .env.example .env
vim .env
```

生产必改项：

```bash
APP_ENV=production
DEBUG=false
LOG_LEVEL=WARNING

SECRET_KEY=<随机32位以上字符串>

POSTGRES_DB=sagittadb
POSTGRES_USER=sagitta
POSTGRES_PASSWORD=<PostgreSQL强密码>

REDIS_PASSWORD=<Redis强密码>
REDIS_URL=redis://:<Redis强密码>@redis:6379/0

DATABASE_URL=postgresql+asyncpg://sagitta:<PostgreSQL强密码>@postgres:5432/sagittadb
DATABASE_URL_SYNC=postgresql+psycopg2://sagitta:<PostgreSQL强密码>@postgres:5432/sagittadb

ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=3
```

认证、通知、AI 等运行时配置在系统管理页面配置，不需要写入环境变量。

### 5.5 Oracle 11g 特殊配置

如果需要连接 Oracle 11.2 或更早版本，需要启用 Thick 模式并提供 Oracle Instant Client：

```bash
ORACLE_DRIVER_MODE=thick
ORACLE_CLIENT_LIB_DIR=
ORACLE_CLIENT_CONFIG_DIR=
```

将 Instant Client 解压到 `backend/vendor/oracle/instantclient_*` 后重新构建后端相关镜像。

### 5.6 启动服务

从项目根目录执行：

```bash
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```

等待 `postgres` 和 `redis` 健康后执行迁移：

```bash
docker compose -f deploy/docker-compose.yml exec backend alembic upgrade head
```

### 5.7 初始化系统

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/init/
```

随后访问前端入口，使用初始化管理员账号登录，并按提示修改默认密码。新密码必须符合复杂度要求：至少 8 位，包含数字、大写字母、小写字母和特殊字符。

### 5.8 配置 HTTPS 入口

生产环境建议使用宿主机 Nginx 或企业网关统一接入 HTTPS。

示例 Nginx 配置：

```nginx
server {
    listen 443 ssl http2;
    server_name db.example.com;

    ssl_certificate /etc/letsencrypt/live/db.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/db.example.com/privkey.pem;

    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
        client_max_body_size 50m;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }
}

server {
    listen 80;
    server_name db.example.com;
    return 301 https://$host$request_uri;
}
```

### 5.9 防火墙建议

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5432/tcp
sudo ufw deny 6379/tcp
sudo ufw deny 5555/tcp
sudo ufw deny 9090/tcp
sudo ufw deny 3000/tcp
sudo ufw enable
```

如果 Flower、Prometheus、Grafana 需要访问，应通过 VPN、堡垒机或内网网段限制。

## 6. Kubernetes + Helm 部署

### 6.1 前置条件

- Kubernetes 集群可用。
- `kubectl` 已配置目标集群上下文。
- 已安装 Helm 3。
- 已准备 Ingress、StorageClass、镜像仓库和 TLS 证书。

### 6.2 配置 Values

```bash
cd deploy/helm
helm dependency update sagittadb/
cp sagittadb/values-prod.yaml /tmp/sagittadb-values.yaml
vim /tmp/sagittadb-values.yaml
```

重点检查：

- 镜像地址与 tag。
- `SECRET_KEY`、数据库密码、Redis 密码。
- Ingress 域名和 TLS。
- PostgreSQL、Redis、下载目录等持久化存储。
- Backend、Worker、Frontend 副本数与资源限制。

### 6.3 安装

```bash
helm install sagittadb deploy/helm/sagittadb -f /tmp/sagittadb-values.yaml
```

升级：

```bash
helm upgrade sagittadb deploy/helm/sagittadb -f /tmp/sagittadb-values.yaml
```

查看状态：

```bash
kubectl get pods
kubectl get svc
kubectl get ingress
```

Helm Chart 中的 initContainer 会在应用启动前执行 `alembic upgrade head`。如果企业要求手动审批迁移，可在上线流程中单独执行迁移任务。

## 7. 发布升级

仓库提供标准生产发布脚本：

```bash
bash deploy/update-prod.sh
```

常用参数：

```bash
bash deploy/update-prod.sh --ref v1.0.1
bash deploy/update-prod.sh --skip-backup
bash deploy/update-prod.sh --no-cache --prune
```

推荐生产升级流程：

1. 通知业务窗口。
2. 备份 PostgreSQL。
3. 拉取目标版本。
4. 构建镜像。
5. 执行 Alembic 迁移。
6. 重启应用服务。
7. 验证健康检查、登录、工单、查询和异步任务。
8. 保留旧版本镜像和备份，直到观察期结束。

## 8. 回滚策略

### 8.1 应用回滚

如果仅应用代码异常，数据库结构未发生不兼容变更，可回滚到上一版本镜像或 Git tag：

```bash
git checkout <previous_tag>
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

### 8.2 数据库回滚

如果迁移已改变数据库结构，优先使用升级前备份恢复。只有在明确确认 Alembic downgrade 安全时，才执行：

```bash
docker compose -f deploy/docker-compose.yml exec backend alembic downgrade -1
```

生产环境建议以备份恢复作为主要回滚手段。

## 9. 部署验收

上线后至少完成以下验收：

- 前端可通过 HTTPS 正常访问。
- `/health` 返回正常。
- 管理员可以登录并修改密码。
- Alembic 版本为最新 head。
- Celery Worker 和 Beat 正常运行。
- 能创建实例并测试连接。
- 能同步数据库/Schema。
- 能完成一条 SQL 工单从提交到执行的闭环。
- 能完成查询权限申请、审批和在线查询。
- 能查看审计日志和查询历史。
- 备份脚本可执行并生成备份文件。
