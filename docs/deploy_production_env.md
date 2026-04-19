# SagittaDB 生产环境部署文档

> **文档版本：** v1.2 · 2026-04-11
> **适用版本：** SagittaDB v1.0-GA
> **部署方式：** 方案一 Docker Compose 生产模式 / 方案二 Kubernetes + Helm Chart
> **目标读者：** 运维工程师、DevOps、系统管理员

---

## 一、部署方案选择

| 维度 | 方案一：Docker Compose 生产模式 | 方案二：Kubernetes + Helm |
|---|---|---|
| **适用规模** | 小型团队（< 50 人），单机部署 | 中大型团队，多节点高可用 |
| **部署复杂度** | 低，1台服务器即可 | 高，需要 K8s 集群 |
| **高可用** | 单点，无横向扩展 | 多副本，HPA 自动扩缩容 |
| **运维成本** | 低 | 中等（需熟悉 K8s） |
| **推荐场景** | 企业内网，非关键业务 | 生产关键业务，需 SLA 保障 |

---

## 二、方案一：Docker Compose 生产模式

### 2.1 服务器要求

| 资源 | 最低配置 | 推荐配置 |
|---|---|---|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 系统盘 | 50 GB SSD | 100 GB SSD |
| 数据盘 | 100 GB | 500 GB（独立挂载） |
| 操作系统 | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| 网络 | 独立公网 IP | 公网 IP + 域名 + SSL |

### 2.2 服务器初始化

```bash
# 更新系统
sudo apt-get update && sudo apt-get upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker compose version

# 创建数据目录（建议挂载独立数据盘）
sudo mkdir -p /data/sagittadb/{postgres,redis,prometheus,grafana,downloads,backups}
sudo chown -R $USER:$USER /data/sagittadb
```

### 2.3 拉取代码

```bash
cd /opt
sudo git clone https://github.com/Lynn-Lee/SagittaDB.git
sudo chown -R $USER:$USER SagittaDB
cd SagittaDB
```

### 2.4 生成密钥

```bash
# 生成 SECRET_KEY（JWT 签名密钥）
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 PostgreSQL 强密码
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

记录生成的值，填入下一步的 `.env` 文件。

### 2.5 配置生产环境变量

```bash
cp .env.example .env
vim .env
```

**生产环境 `.env` 必须修改的配置项：**

```bash
# ── 数据库（生产环境必须修改密码）───────────────────
DATABASE_URL=postgresql+asyncpg://sagitta:<强密码>@postgres:5432/sagittadb
DATABASE_URL_SYNC=postgresql+psycopg2://sagitta:<强密码>@postgres:5432/sagittadb

# ── Redis（生产环境必须修改密码）────────────────────
REDIS_URL=redis://:<Redis强密码>@redis:6379/0
REDIS_PASSWORD=<Redis强密码>

# ── 安全（生产环境必须替换，系统启动时会强制校验）────
# 若使用默认值且 APP_ENV=production，后端启动时将抛出 ValueError 并拒绝启动
SECRET_KEY=<上一步生成的随机字符串，至少32位>
ACCESS_TOKEN_EXPIRE_MINUTES=30     # 生产建议缩短至 30 分钟
REFRESH_TOKEN_EXPIRE_DAYS=3        # 生产建议缩短至 3 天

# ── 应用环境 ─────────────────────────────────────────
APP_ENV=production
DEBUG=false
LOG_LEVEL=WARNING

# ── 可观测中心 ───────────────────────────────────────
PROMETHEUS_URL=http://prometheus:9090
ALERTMANAGER_URL=http://alertmanager:9093
GRAFANA_URL=https://your-domain.com:3000     # 修改为实际域名

# ── PostgreSQL Docker 初始化 ─────────────────────────
POSTGRES_DB=sagittadb
POSTGRES_USER=sagitta
POSTGRES_PASSWORD=<与 DATABASE_URL 中一致的强密码>

# ── 通知配置（通过系统配置页面管理）──────────────────
# 以下配置已废弃，请通过 Web UI「系统配置」页面配置
# DINGTALK_WEBHOOK=...
# FEISHU_WEBHOOK=...
# SMTP_HOST=...
# 登录后访问：系统配置 → 钉钉通知 / 飞书通知 / 邮件通知
```

### 2.6 配置数据卷持久化

修改 `docker-compose.yml`，将数据卷挂载到独立数据盘：

```bash
# 在 volumes 节点末尾，将命名卷改为绑定挂载
# 编辑 docker-compose.yml，将以下内容
#   pg_data:
# 改为
#   pg_data:
#     driver: local
#     driver_opts:
#       type: none
#       o: bind
#       device: /data/sagittadb/postgres
```

或更简单地，在 `.env` 中添加：

```bash
PG_DATA_PATH=/data/sagittadb/postgres
REDIS_DATA_PATH=/data/sagittadb/redis
GRAFANA_DATA_PATH=/data/sagittadb/grafana
PROM_DATA_PATH=/data/sagittadb/prometheus
```

### 2.7 启动生产服务

```bash
# 使用生产覆盖文件叠加启动
docker compose -f deploy/docker-compose.yml up -d

# 查看启动状态
docker compose ps

# 等待 postgres healthy（约 10-20 秒）
watch -n 2 "docker compose ps | grep postgres"
```

### 2.8 初始化数据库

```bash
# 执行迁移
docker compose exec backend alembic upgrade head

# 初始化系统（创建管理员账号）
curl -X POST http://localhost:8000/api/v1/system/init/
```

**⚠️ 重要：立即修改默认管理员密码**

```bash
# 使用 admin / Admin@2024! 首次登录会进入强制改密流程；
# 新密码必须至少 8 位，并同时包含数字、大写字母、小写字母和特殊字符。
```

### 2.9 配置 Nginx 反向代理 + SSL

生产环境需要通过域名 + HTTPS 访问，推荐在宿主机安装 Nginx 作为外层代理：

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 申请 Let's Encrypt 证书
sudo certbot --nginx -d your-domain.com

# 配置 /etc/nginx/sites-available/sagittadb
```

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # 安全头
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

    # 前端
    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50m;
        proxy_read_timeout 120s;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/sagittadb /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 2.10 配置防火墙

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP（重定向至 HTTPS）
sudo ufw allow 443/tcp     # HTTPS
sudo ufw deny 8000/tcp     # 禁止直接访问后端（通过 Nginx 代理）
sudo ufw deny 5432/tcp     # 禁止外部访问 PostgreSQL
sudo ufw deny 6379/tcp     # 禁止外部访问 Redis
sudo ufw enable
```

### 2.11 配置自动备份

```bash
# 设置备份环境变量
export POSTGRES_HOST=localhost
export POSTGRES_PASSWORD=<数据库密码>
export BACKUP_DIR=/data/sagittadb/backups
export BACKUP_RETAIN_DAYS=30

# 添加 crontab（每天凌晨 2 点自动备份）
crontab -e
# 添加以下行：
0 2 * * * POSTGRES_HOST=localhost POSTGRES_PASSWORD=<密码> BACKUP_DIR=/data/sagittadb/backups bash /opt/SagittaDB/deploy/backup/backup-postgres.sh >> /var/log/sagittadb-backup.log 2>&1
```

若需上传至 S3：

```bash
0 2 * * * POSTGRES_HOST=localhost POSTGRES_PASSWORD=<密码> S3_BUCKET=your-bucket bash /opt/SagittaDB/deploy/backup/backup-postgres.sh
```

### 2.12 生产模式各服务规格

| 服务 | CPU 限制 | 内存限制 | 说明 |
|---|---|---|---|
| postgres | 2 核 | 2 GB | 主数据库 |
| redis | 1 核 | 512 MB | 缓存/消息队列 |
| backend | 2 核 | 1 GB | 4 个 uvicorn workers |
| celery_worker | 4 核 | 2 GB | 8 并发任务 |
| celery_beat | 0.5 核 | 256 MB | 定时任务调度 |
| flower | 0.5 核 | 256 MB | Celery 监控 |
| frontend | 0.5 核 | 128 MB | Nginx 静态文件 |
| prometheus | 1 核 | 1 GB | 指标存储 |
| grafana | 1 核 | 512 MB | 可视化 |

---

## 三、方案二：Kubernetes + Helm Chart

### 3.1 集群要求

| 资源 | 最低要求 | 推荐生产配置 |
|---|---|---|
| K8s 版本 | 1.27+ | 1.29+ |
| 节点数 | 3 | 5（2 master + 3 worker） |
| 每节点 CPU | 4 核 | 8 核 |
| 每节点内存 | 8 GB | 16 GB |
| 存储 | 支持 ReadWriteOnce PVC | gp3 StorageClass（AWS EKS） |
| Ingress | nginx-ingress-controller | nginx-ingress-controller |
| 证书管理 | cert-manager | cert-manager（Let's Encrypt） |

### 3.2 前置依赖安装

```bash
# 安装 kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 安装 Helm 3
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 验证
kubectl version --client
helm version
```

### 3.3 添加 Bitnami Chart 仓库

Helm Chart 依赖 bitnami/postgresql 和 bitnami/redis：

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### 3.4 创建命名空间

```bash
kubectl create namespace sagittadb
```

### 3.5 生成并创建 Secret

**⚠️ 绝不要将密钥明文写入 values 文件并提交 Git。使用 K8s Secret 或 Sealed Secrets。**

```bash
# 生成 SECRET_KEY
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 生成数据库密码
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

# 生成 Redis 密码
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(20))")

# 创建 K8s Secret
kubectl create secret generic sagittadb-secrets \
  --namespace sagittadb \
  --from-literal=secret-key="${SECRET_KEY}" \
  --from-literal=db-password="${DB_PASSWORD}" \
  --from-literal=redis-password="${REDIS_PASSWORD}"
```

### 3.6 安装 nginx-ingress-controller

```bash
helm upgrade --install ingress-nginx ingress-nginx \
  --repo https://kubernetes.github.io/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace

# 获取 Ingress 外部 IP（等待约 2 分钟）
kubectl get svc -n ingress-nginx ingress-nginx-controller
```

将域名 DNS A 记录指向该 IP。

### 3.7 安装 cert-manager（自动 HTTPS 证书）

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# 等待 cert-manager 就绪
kubectl wait --namespace cert-manager \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/instance=cert-manager \
  --timeout=120s
```

创建 ClusterIssuer：

```yaml
# clusterissuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com    # 修改为实际邮箱
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
```

```bash
kubectl apply -f clusterissuer.yaml
```

### 3.8 定制 prod values

编辑 `deploy/helm/sagittadb/values-prod.yaml`，修改以下关键项：

```yaml
image:
  registry: ghcr.io
  repository: lynn-lee/sagittadb/backend   # 修改为实际仓库
  tag: "1.0.0"

frontend:
  image:
    registry: ghcr.io
    repository: lynn-lee/sagittadb/frontend
    tag: "1.0.0"

ingress:
  hosts:
    - host: sagittadb.yourdomain.com       # 修改为实际域名
      paths:
        - path: /api
          pathType: Prefix
          backend: backend
        - path: /
          pathType: Prefix
          backend: frontend
  tls:
    - secretName: sagittadb-prod-tls
      hosts:
        - sagittadb.yourdomain.com

externalDatabase:
  host: "your-rds-endpoint.rds.amazonaws.com"   # 修改为实际 RDS 地址
  port: 5432
  database: sagittadb
  username: sagitta

externalRedis:
  host: "your-elasticache.cache.amazonaws.com"   # 修改为实际 Redis 地址
  port: 6379
  db: 0
```

### 3.9 部署 Chart

```bash
cd deploy/helm

helm upgrade --install sagittadb ./sagittadb \
  --namespace sagittadb \
  --create-namespace \
  -f sagittadb/values-prod.yaml \
  --set app.secretKey="$(kubectl get secret sagittadb-secrets -n sagittadb -o jsonpath='{.data.secret-key}' | base64 -d)" \
  --set externalDatabase.password="$(kubectl get secret sagittadb-secrets -n sagittadb -o jsonpath='{.data.db-password}' | base64 -d)" \
  --set externalRedis.password="$(kubectl get secret sagittadb-secrets -n sagittadb -o jsonpath='{.data.redis-password}' | base64 -d)" \
  --wait \
  --timeout 10m
```

### 3.10 验证部署状态

```bash
# 查看所有 Pod 状态
kubectl get pods -n sagittadb

# 查看 Ingress 状态（确认 HTTPS 证书）
kubectl get ingress -n sagittadb

# 查看 HPA 状态
kubectl get hpa -n sagittadb

# 查看服务日志
kubectl logs -n sagittadb deployment/sagittadb-backend --tail=50
kubectl logs -n sagittadb deployment/sagittadb-worker --tail=50
```

### 3.11 初始化系统

```bash
# 等待 backend Pod 就绪后
BACKEND_POD=$(kubectl get pod -n sagittadb -l app.kubernetes.io/component=backend -o jsonpath='{.items[0].metadata.name}')

# 执行数据库迁移（initContainer 会自动执行，此命令用于验证）
kubectl exec -n sagittadb $BACKEND_POD -- alembic current

# 初始化系统
kubectl exec -n sagittadb $BACKEND_POD -- \
  python -c "import httpx; r = httpx.post('http://localhost:8000/api/v1/system/init/'); print(r.json())"
```

或通过外部访问：

```bash
curl -X POST https://sagittadb.yourdomain.com/api/v1/system/init/
```

### 3.12 Helm 升级与回滚

```bash
# 升级到新版本
helm upgrade sagittadb ./sagittadb \
  --namespace sagittadb \
  -f sagittadb/values-prod.yaml \
  --set image.tag="1.0.1" \
  --set app.secretKey="..."

# 查看发布历史
helm history sagittadb -n sagittadb

# 回滚到上一版本
helm rollback sagittadb -n sagittadb

# 回滚到指定版本
helm rollback sagittadb 2 -n sagittadb
```

---

## 四、生产环境安全加固清单

部署完成后，逐项确认以下安全措施：

### 4.1 密钥与凭证

- [ ] `SECRET_KEY` 已替换为随机 32+ 字符字符串
- [ ] 数据库密码强度 ≥ 20 位（含大小写+数字+特殊字符）
- [ ] Redis 密码已设置
- [ ] 默认管理员密码 `Admin@2024!` 已修改，且新密码符合复杂度要求并纳入 30 天轮换
- [ ] 敏感配置未明文出现在 Git 仓库中
- [ ] `.env` 文件权限为 `600`（`chmod 600 .env`）

### 4.2 网络访问控制

- [ ] PostgreSQL（5432）不对外网暴露
- [ ] Redis（6379）不对外网暴露
- [ ] Flower（5555）不对外网暴露，仅内网/VPN 可访问
- [ ] Grafana（3000）不对外网暴露，仅内网/VPN 可访问
- [ ] 所有外部访问通过 HTTPS（443）
- [ ] HTTP（80）强制重定向至 HTTPS

### 4.3 数据安全

- [ ] PostgreSQL 定期备份已配置（每日 cron）
- [ ] 备份文件已测试恢复流程
- [ ] 若使用 S3，备份桶已开启版本控制和加密

### 4.4 监控告警

- [ ] Prometheus 正常采集指标
- [ ] Grafana Dashboard 已导入
- [ ] Alertmanager 告警规则已配置（磁盘 / 内存 / 服务宕机）
- [ ] 告警通知渠道（邮件/钉钉）已验证可达

---

## 五、数据库备份与恢复

### 5.1 手动备份

```bash
# Docker Compose 环境
POSTGRES_HOST=localhost \
POSTGRES_PASSWORD=<密码> \
BACKUP_DIR=/data/sagittadb/backups \
bash deploy/backup/backup-postgres.sh

# K8s 环境
kubectl exec -n sagittadb $BACKEND_POD -- \
  bash -c "PGPASSWORD=<密码> pg_dump -h <DB_HOST> -U sagitta sagittadb | gzip" \
  > /local/path/sagittadb_$(date +%Y%m%d).sql.gz
```

### 5.2 从备份恢复

```bash
# Docker Compose 环境
bash deploy/backup/restore-postgres.sh \
  /data/sagittadb/backups/sagittadb_sagitta_20260326_020000.sql.gz

# 手动恢复（任意环境）
zcat sagittadb_xxx.sql.gz | \
  PGPASSWORD=<密码> psql -h localhost -U sagitta -d sagittadb
```

### 5.3 备份验证（每月执行一次）

```bash
# 1. 创建验证库
docker compose exec postgres createdb -U sagitta sagittadb_verify

# 2. 恢复到验证库
bash deploy/backup/restore-postgres.sh /path/to/backup.sql.gz sagittadb_verify

# 3. 验证关键数据
docker compose exec postgres psql -U sagitta -d sagittadb_verify \
  -c "SELECT COUNT(*) FROM sql_users; SELECT COUNT(*) FROM sql_workflow;"

# 4. 清理验证库
docker compose exec postgres dropdb -U sagitta sagittadb_verify
```

---

## 六、运维手册

### 6.1 滚动更新（Docker Compose）

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 重新构建镜像
docker compose -f deploy/docker-compose.yml build backend frontend

# 3. 滚动重启（逐个服务）
docker compose -f deploy/docker-compose.yml up -d --no-deps backend
docker compose -f deploy/docker-compose.yml up -d --no-deps frontend
docker compose -f deploy/docker-compose.yml up -d --no-deps celery_worker
```

### 6.2 查看生产日志

```bash
# 实时日志（带时间戳）
docker compose logs -f --timestamps backend | grep -v "health"

# 只看错误
docker compose logs backend 2>&1 | grep -i "error\|exception\|traceback"

# 按时间范围
docker compose logs --since="2026-03-26T10:00:00" --until="2026-03-26T11:00:00" backend
```

### 6.3 紧急故障处理

```bash
# 后端服务无响应 → 重启
docker compose -f deploy/docker-compose.yml restart backend

# PostgreSQL 磁盘满 → 清理
du -sh /data/sagittadb/postgres     # 检查占用
docker compose exec postgres vacuumdb -U sagitta --analyze sagittadb  # 清理垃圾

# Redis 内存告警 → 查看占用
docker compose exec redis redis-cli -a <密码> info memory
docker compose exec redis redis-cli -a <密码> flushdb  # ⚠️ 仅在缓存数据无关紧要时使用

# Celery 任务堆积 → 清空队列
docker compose exec redis redis-cli -a <密码> del celery
docker compose -f deploy/docker-compose.yml restart celery_worker
```

### 6.4 性能调优

| 场景 | 调整参数 | 文件 |
|---|---|---|
| 并发请求量大 | 增加 `--workers` 数量（≤ 2×CPU核数） | `deploy/docker-compose.yml` backend command |
| SQL 执行慢 | 增加 celery_worker concurrency | `deploy/docker-compose.yml` celery_worker command |
| PostgreSQL 慢查询 | 调整 `max_connections`、`shared_buffers` | postgres 环境变量 |
| Redis 内存不足 | 增加 memory limit 或使用独立 Redis 集群 | `docker-compose.yml` redis |

---

## 七、版本升级流程

```
1. 查看 Release Notes（GitHub Releases）
2. 备份当前数据库
3. 测试环境验证新版本
4. 维护窗口通知用户
5. 生产环境执行升级
6. 执行 alembic upgrade head（如有 schema 变更）
7. 验证核心功能
8. 恢复服务，通知用户
```

具体步骤：

```bash
# 备份
bash deploy/backup/backup-postgres.sh

# 拉取新版本代码
git pull origin main
git checkout v1.0.1   # 切换到目标版本 tag

# 重新构建并启动
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d

# 执行迁移
docker compose exec backend alembic upgrade head

# 验证
curl https://your-domain.com/health
```

---

## 八、监控指标参考

| 指标 | 告警阈值 | 说明 |
|---|---|---|
| 磁盘使用率 | > 80% | 及时扩容或清理 |
| 内存使用率 | > 85% | 检查内存泄漏 |
| CPU 使用率 | > 70%（持续5分钟） | 考虑横向扩展 |
| PostgreSQL 连接数 | > max_connections × 80% | 调整连接池 |
| Celery 队列积压 | > 100 个任务 | 增加 Worker 副本 |
| 登录接口 P95 | > 1s | 排查 DB 慢查询 |
| 工单执行失败率 | > 5% | 检查引擎连接 |

Prometheus 告警规则文件位于 `deploy/prometheus/rules/`，Grafana Dashboard 模板位于 `deploy/grafana/`。

---

## 九、端口与服务清单

### 对外暴露（通过 Nginx 反向代理）

| URL 路径 | 后端服务 | 说明 |
|---|---|---|
| `https://domain.com/` | frontend:80 | React SPA |
| `https://domain.com/api/` | backend:8000 | REST API |
| `https://domain.com/ws/` | backend:8000 | WebSocket |
| `https://domain.com/docs` | backend:8000 | API 文档（生产建议关闭） |

### 仅内网/VPN 访问

| 端口 | 服务 | 说明 |
|---|---|---|
| 5555 | Flower | Celery 任务监控 |
| 3000 | Grafana | 监控仪表板 |
| 9090 | Prometheus | 指标查询 |
| 9093 | Alertmanager | 告警管理 |

### 禁止外网访问

| 端口 | 服务 |
|---|---|
| 5432 | PostgreSQL |
| 6379 | Redis |
| 8000 | FastAPI 直接访问 |

---

*SagittaDB 矢准数据 · 生产环境部署文档 v1.0 · 2026-03-26*
