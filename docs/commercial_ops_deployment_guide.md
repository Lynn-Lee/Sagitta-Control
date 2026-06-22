# Sagitta Control Enterprise 运维部署维护升级文档

> 文档版本：v1.0  
> 适用产品：Sagitta Control Enterprise 正式商业版 2.2.0  
> 目标读者：运维工程师、DevOps、DBA、系统管理员、实施顾问  
> 授权项目码：`sagittadb`

本文面向客户正式试用和生产推广，说明 Sagitta Control Enterprise 的部署、授权、初始化、巡检、备份恢复、升级回滚、维护、安全检查和常见故障处理。阶段一品牌切换仅调整对外产品名，客户包文件名、Helm release、Kubernetes namespace 和授权项目码仍保留 `SagittaDB-Enterprise` / `sagittadb` 兼容示例。

## 1. 部署架构

Sagitta Control Enterprise 由以下核心服务组成：

| 服务 | 作用 |
|---|---|
| `frontend` | 前端页面、静态资源和 API 反向代理。 |
| `backend` | FastAPI 后端服务，提供认证、工单、查询、实例、系统配置和授权接口。 |
| `celery_worker` | 异步执行 SQL、通知、归档、监控采集等后台任务。 |
| `celery_beat` | 周期任务调度。 |
| `postgres` | 平台元数据数据库。 |
| `redis` | Celery broker、Token 黑名单和临时状态。 |

可选外围组件：

| 组件 | 用途 |
|---|---|
| Nginx / Caddy / Ingress | HTTPS、反向代理、域名入口。 |
| Prometheus / Grafana / Alertmanager | 客户统一监控体系。 |
| 对象存储或备份盘 | 保存数据库备份、部署包、验收材料和诊断包。 |

推荐部署方式：

| 方式 | 场景 |
|---|---|
| Docker Compose | 单机、虚拟机、客户内网试用、中小规模生产部署。 |
| Kubernetes + Helm | 多节点、高可用、云原生运维和统一集群管理场景。 |

## 2. 部署前准备

### 2.1 基础环境

建议环境：

- Linux x86_64 服务器。
- Docker Engine 和 Docker Compose Plugin。
- 可访问商业镜像仓库。
- 可访问 License-Server-Center，或已准备离线授权流程。
- 已规划域名、HTTPS 证书、访问端口和防火墙策略。
- 已规划 PostgreSQL 数据卷、备份目录和日志保留策略。

最低准备信息：

| 信息 | 示例 |
|---|---|
| 客户 ID | `acme-prod` |
| 平台域名 | `https://sagittadb.example.com` |
| 管理员账号 | 首次初始化后创建或由系统初始化接口生成 |
| 首个数据库实例 | 用于验证连接、查询、工单和观测链路 |
| 通知渠道 | 邮件、钉钉、飞书或企业微信至少一种 |
| 授权方式 | 60 天试用、在线激活或离线 challenge-response |

### 2.2 网络与安全

生产环境建议：

- 仅暴露 HTTPS 前端入口。
- PostgreSQL、Redis、backend 调试端口、Flower、Prometheus、Grafana 不直接暴露公网。
- 后端 API 只通过前端反向代理或受控内网访问。
- 使用安全组或防火墙限制数据库访问来源。
- 使用客户统一证书体系或可信公网证书。
- 禁止把 `.env`、License、私钥、数据库密码提交到 Git。

### 2.3 关键环境变量

必须重点配置：

| 变量 | 说明 |
|---|---|
| `APP_ENV` | 生产环境设置为 `production`。 |
| `SECRET_KEY` | 32 位以上随机值，必须长期稳定。 |
| `DATABASE_URL` | 后端异步 PostgreSQL 连接串。 |
| `DATABASE_URL_SYNC` | Alembic 同步 PostgreSQL 连接串。 |
| `REDIS_URL` | Redis 连接串。 |
| `LICENSE_CUSTOMER_ID` | 正式客户 ID。 |
| `LICENSE_DEPLOYMENT_ID` | 稳定部署 ID，用于生成部署指纹。 |
| `LICENSE_PUBLIC_KEY` | 授权公钥，客户包通常已预置。 |
| `LICENSE_SERVER_URL` | 授权中心地址，默认 `https://license.loveai.asia`。 |
| `LICENSE_ONLINE_GRACE_DAYS` | 在线授权联网刷新宽限期，默认 7 天。 |
| `LICENSE_ALLOW_LEGACY_LICENSE_IMPORT` | 生产环境建议保持 `false`。 |

特别注意：

- `SECRET_KEY` 用于派生敏感字段加密密钥，修改后会导致实例密码、SSH 密钥和敏感系统配置无法解密。
- `LICENSE_DEPLOYMENT_ID` 应在正式部署后保持稳定，否则正式激活部署指纹会变化。
- 生产环境不得使用默认密码、默认密钥或 `CHANGE_ME` 占位值。

## 3. Docker Compose 部署

### 3.1 解压客户包

```bash
sha256sum -c SagittaDB-Enterprise-v2.2.0.zip.sha256
unzip SagittaDB-Enterprise-v2.2.0.zip
cd SagittaDB-Enterprise-v2.2.0
```

### 3.2 准备配置

```bash
cp .env.example .env
vim .env
```

建议先执行客户包内置脚本生成生产密钥和稳定部署 ID：

```bash
./prepare-go-live-env.sh --customer-id <customer_id>
```

然后检查 `.env`：

- `APP_ENV=production`。
- `SECRET_KEY` 已替换。
- PostgreSQL、Redis、Grafana 等默认密码已替换。
- `LICENSE_CUSTOMER_ID` 与正式客户 ID 一致。
- `LICENSE_DEPLOYMENT_ID` 已生成且后续不再随意修改。
- `LICENSE_SERVER_URL` 指向正式授权中心或客户私有授权中心。

### 3.3 启动基础服务

```bash
docker compose pull
docker compose up -d postgres redis
```

### 3.4 执行数据库迁移

```bash
docker compose run --rm backend alembic upgrade head
```

### 3.5 启动全部服务

```bash
docker compose up -d
docker compose ps
```

### 3.6 验证健康状态

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

如使用域名和 HTTPS：

```bash
curl -I https://sagittadb.example.com
```

### 3.7 初始化管理员

首次部署后按客户包 README 或实施流程创建管理员账号。若使用系统初始化接口：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/system/init/
```

首次登录后必须修改默认密码。

## 4. Kubernetes + Helm 部署

适用于已有 Kubernetes 运维体系的客户。

部署前准备：

- 镜像仓库地址和固定版本标签。
- PostgreSQL、Redis 部署方式。
- Ingress、域名和 TLS Secret。
- Secret 中的 `SECRET_KEY`、数据库密码、Redis 密码和授权配置。
- 持久化卷和备份策略。
- Worker 和 Beat 的资源限制。

示例命令：

```bash
helm upgrade --install sagittadb ./helm/sagittadb \
  --namespace sagittadb \
  --create-namespace \
  -f values-prod.yaml
```

升级后验证：

```bash
kubectl -n sagittadb get pods
kubectl -n sagittadb logs deploy/sagittadb-backend --tail=100
kubectl -n sagittadb logs deploy/sagittadb-worker --tail=100
```

注意事项：

- Helm values 中必须使用固定版本镜像，不使用 `latest`。
- 生产 Secret 不应写入 Git。
- Ingress 只暴露前端入口。
- 数据库迁移应在发布流程中明确执行。

## 5. License 授权运维

### 5.1 试用授权

首次部署没有正式 License 时，系统自动进入 60 天全功能试用。

试用期间：

- 所有受保护功能可用。
- 管理员可在授权页查看试用到期时间。
- 可完成实例接入、治理配置、工单、查询、归档、观测和验收。

试用到期后：

- 业务 API 被阻断。
- 登录、健康检查和授权管理入口仍可访问。
- 管理员可完成在线激活或导入离线授权。

### 5.2 在线激活

操作步骤：

1. 管理员登录 Sagitta Control。
2. 打开 `商业交付` → `License 授权`。
3. 输入正式客户 ID。
4. 复制正式激活部署指纹。
5. 商务或运营侧在授权中心创建 Sagitta Control 激活码。
6. 客户管理员输入激活码和客户 ID。
7. 点击在线激活。
8. 验证授权状态为 `licensed`，试用状态为 `false`。

授权项目固定为：

```text
project=sagittadb
product=sagittadb
```

标准功能模块：

```text
workflow, query, archive, monitor, ai, masking, instance
```

标准额度字段：

```text
max_users
max_instances
```

### 5.3 联网刷新

在线授权默认需要在 `LICENSE_ONLINE_GRACE_DAYS` 指定周期内成功刷新一次。默认值为 7 天。

刷新失败排查：

- 检查服务器是否能访问 `LICENSE_SERVER_URL`。
- 检查客户 ID 是否一致。
- 检查部署指纹是否变化。
- 检查授权中心激活码状态是否被暂停或吊销。
- 检查本地时间是否严重偏差。

### 5.4 离线授权

适用于长期离线客户。

流程：

1. 客户在授权管理页生成 Challenge。
2. 客户将 Challenge 文件发送给商务或支持团队。
3. 运营侧签发 challenge-response 文件。
4. 客户导入 response 文件。
5. 系统校验签名、客户 ID、授权项目和部署指纹。

生产环境建议：

```text
LICENSE_ALLOW_LEGACY_LICENSE_IMPORT=false
```

不要在生产环境导入未绑定 Challenge 的裸 License JSON。

## 6. 正式推广上线门禁

正式推广或客户验收前，应完成页面验收和脚本验收。

### 6.1 页面验收

在 `商业交付` → `交付与支持` 中检查：

- License 为正式授权或仍处于有效试用期。
- 客户 ID 和正式激活部署指纹非空。
- 至少存在一个活跃实例。
- 用户、角色、用户组、资源组和审批流已配置。
- 至少一种通知渠道完成测试。
- 观测采集无持续失败。
- 已生成 Markdown 或 JSON 验收报告。
- 推广就绪度为 `可推广` 或现场已确认可接受的状态。

### 6.2 脚本门禁

客户包目录执行：

```bash
./go-live-check.sh \
  --api-base-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1/ \
  --username <admin> \
  --password '<admin-password>'
```

如果管理员启用 2FA，可改用：

```bash
./go-live-check.sh \
  --api-base-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1/ \
  --token '<access_token>'
```

失败项必须处理，不建议通过假配置绕过。

常见失败项：

| 失败项 | 处理 |
|---|---|
| `SECRET_KEY` 默认或长度不足 | 重新生成生产密钥，并确认敏感字段可用。 |
| License 仍为试用 | 完成正式在线激活或离线授权。 |
| 客户 ID 不一致 | 修正 `.env` 和授权中心记录。 |
| 缺少活跃实例 | 接入至少一个客户现场实例并测试连接。 |
| 实施向导未完成 | 在交付页补齐品牌、授权、认证、通知、实例和验收项。 |
| 通知链路未验证 | 配置邮件、飞书、钉钉或企微并执行测试。 |
| 推广就绪度非 ready | 处理交付页待处理项。 |

## 7. 日常巡检

建议每日基础巡检，每周完整巡检。

### 7.1 服务状态

```bash
docker compose ps
```

检查：

- `backend`、`frontend`、`celery_worker`、`celery_beat`、`postgres`、`redis` 正常运行。
- 核心服务没有频繁重启。
- 健康检查通过。

### 7.2 健康接口

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

### 7.3 Worker 队列

```bash
docker compose exec celery_worker celery -A app.celery_app inspect active
docker compose exec celery_worker celery -A app.celery_app inspect reserved
docker compose exec celery_worker celery -A app.celery_app inspect scheduled
```

关注：

- `execute` 队列是否积压。
- `archive` 队列是否长期执行。
- `notify` 队列是否失败。
- `monitor` 队列是否持续报错。

### 7.4 数据库容量

```bash
docker compose exec postgres psql -U <postgres_user> -d <postgres_db> \
  -c "select pg_size_pretty(pg_database_size(current_database()));"
```

重点关注：

- 查询历史。
- 审计日志。
- 通知日志。
- 会话快照。
- SQL 洞察样本。
- 归档批次日志。

### 7.5 License 状态

管理员定期查看：

- License 是否有效。
- 剩余天数是否小于 30 天。
- 在线授权是否成功刷新。
- 用户数和实例数是否接近授权额度。
- 授权中心状态是否为 active。

## 8. 日志管理

常用命令：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 celery_worker
docker compose logs --tail=200 celery_beat
docker compose logs --tail=200 frontend
docker compose logs --tail=200 postgres
docker compose logs --tail=200 redis
```

常见关键词：

| 关键词 | 说明 |
|---|---|
| `license_check_failed` | License 校验异常。 |
| `InvalidToken` | JWT、Fernet 或敏感配置解密异常。 |
| `OperationalError` | PostgreSQL 或目标数据库连接异常。 |
| `Redis` | Redis 连接或 Token 黑名单异常。 |
| `Task failed` | Celery 任务失败。 |
| `permission` | 权限或目标数据库账号权限不足。 |
| `deployment_fingerprint` | 部署指纹或授权绑定问题。 |

日志处理建议：

- 生产环境接入客户统一日志平台。
- 日志中如包含 SQL、账号、主机或错误堆栈，应按客户安全规范授权访问。
- 诊断包对密钥、Token、Secret 和连接串做脱敏，但仍建议仅在授权支持渠道流转。

## 9. 备份与恢复

### 9.1 备份对象

必须备份：

- PostgreSQL 平台元数据。
- `.env` 或生产 Secret。
- 客户包、版本号、镜像摘要和 sha256。
- License 激活记录或离线 response 文件。
- Nginx、Helm values、Ingress、证书等部署配置。

不建议只备份容器。核心业务状态在 PostgreSQL 和配置文件中。

### 9.2 备份策略

建议：

- 每日全量备份 PostgreSQL。
- 至少保留 7 天，生产关键环境建议 30 天以上。
- 升级前强制备份。
- 每月至少演练一次恢复。
- 备份文件加密存储并限制访问权限。

### 9.3 执行备份

如客户包或仓库包含备份脚本：

```bash
bash deploy/backup/backup-postgres.sh
```

或按客户运维标准使用 `pg_dump`：

```bash
docker compose exec postgres pg_dump -U <postgres_user> <postgres_db> \
  | gzip > sagittadb_$(date +%Y%m%d_%H%M%S).sql.gz
```

备份后检查：

```bash
ls -lh *.sql.gz
gzip -t sagittadb_*.sql.gz
```

### 9.4 恢复流程

恢复前确认：

- 已停止写入流量。
- 已备份当前异常现场。
- 目标备份文件完整。
- `SECRET_KEY` 与备份时期一致。

恢复示例：

```bash
docker compose stop backend celery_worker celery_beat frontend
gunzip -c sagittadb_backup.sql.gz | docker compose exec -T postgres psql -U <postgres_user> <postgres_db>
docker compose up -d
```

恢复后验证：

- 管理员可登录。
- 实例密码可解密。
- SQL 工单、查询权限、审计日志可查看。
- License 状态正常。
- 后台任务正常执行。

## 10. 升级

### 10.1 升级前检查

升级前必须确认：

- 当前版本和目标版本明确。
- 已阅读发布说明。
- 已完成 PostgreSQL 备份。
- 已记录当前镜像摘要和部署包 sha256。
- 已确认维护窗口。
- 已准备回滚版本和恢复方案。
- 客户已通知相关用户暂停高风险操作。

### 10.2 Docker Compose 升级

标准流程：

```bash
cd SagittaDB-Enterprise-v<target_version>
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

升级后验证：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

页面验证：

- 管理员登录成功。
- License 状态正常。
- 实例列表正常。
- SQL 工单列表正常。
- 在线查询可执行。
- Celery Worker 正常处理任务。
- 观测中心无持续采集错误。

### 10.3 Helm 升级

```bash
helm upgrade sagittadb ./helm/sagittadb \
  --namespace sagittadb \
  -f values-prod.yaml
```

升级后：

```bash
kubectl -n sagittadb rollout status deploy/sagittadb-backend
kubectl -n sagittadb rollout status deploy/sagittadb-frontend
kubectl -n sagittadb rollout status deploy/sagittadb-worker
```

### 10.4 数据库迁移

升级必须执行 Alembic 迁移：

```bash
docker compose run --rm backend alembic upgrade head
```

注意事项：

- 不建议在未确认可逆性的情况下直接执行 `alembic downgrade`。
- 遇到迁移失败时，应保留现场日志，优先用升级前备份恢复。

## 11. 回滚

### 11.1 回滚原则

- 如果只是应用版本异常，优先回滚到上一版本镜像或客户包。
- 如果涉及数据库迁移异常，优先使用升级前备份恢复数据库。
- 回滚前先判断是否有新写入数据需要保留。
- 不要在不清楚迁移影响时直接修改数据库结构。

### 11.2 应用回滚

使用上一版本客户包：

```bash
cd SagittaDB-Enterprise-v<previous_version>
docker compose pull
docker compose up -d
docker compose ps
```

如数据库 schema 未变化，通常无需恢复数据库。

### 11.3 数据库恢复式回滚

适用于迁移导致数据结构或数据不可用的场景。

流程：

1. 停止前端、后端和 Worker。
2. 备份当前异常数据库。
3. 恢复升级前备份。
4. 使用上一版本客户包启动服务。
5. 执行健康检查和业务验证。

## 12. 容量与保留策略

易增长数据：

| 数据 | 说明 |
|---|---|
| 查询历史 | 在线查询、导出和失败记录。 |
| 审计日志 | 登录、配置、工单、权限、归档和授权操作。 |
| 通知日志 | 邮件、钉钉、飞书、企微投递结果。 |
| 会话快照 | 运行诊断周期采样。 |
| SQL 洞察 | SQL 样本、指纹和采集状态。 |
| 归档日志 | 作业批次和执行明细。 |

建议：

- 定期检查 PostgreSQL 数据库大小。
- 根据客户合规要求设置审计和查询历史保留周期。
- 诊断采样和 SQL 洞察数据设置合理保留天数。
- 导出文件、临时文件和诊断包定期清理。
- 大客户生产环境使用独立数据盘和备份盘。

## 13. 安全维护

每月检查：

- `APP_ENV=production`。
- 未使用默认 `SECRET_KEY`。
- PostgreSQL、Redis、Grafana 等未使用默认密码。
- 外网未暴露 PostgreSQL、Redis、后端调试端口、Flower、Prometheus、Grafana。
- 管理员账号数量合理。
- 离职或转岗账号已禁用。
- 用户角色和用户组资源范围符合最小权限原则。
- 查询权限没有不必要的长期大范围授权。
- 审批流负责人仍然有效。
- License 未临近过期。
- 备份文件可恢复。
- 第三方认证和通知密钥未过期。
- 系统日志无持续重复错误。

发布前额外检查：

- 客户包 sha256 校验通过。
- 镜像版本为固定版本，不使用 `latest`。
- 商业镜像和客户包签名材料保留。
- SBOM 材料保留。
- `go-live-check.sh` 通过或失败项已记录和处理。

## 14. 常见故障处理

### 14.1 用户无法登录

排查顺序：

1. 检查前端和后端健康接口。
2. 检查 Redis 是否可用。
3. 查看后端日志中的认证错误。
4. 检查账号是否禁用、密码是否过期、是否需要强制改密。
5. 第三方登录检查 LDAP/OIDC/CAS/企业应用配置。
6. 开启 2FA 的账号检查动态验证码时间同步。

### 14.2 日期控件仍显示英文

最终产品口径要求日期选择器和日期范围选择器使用简体中文，包括月份、星期、`今天`、`请选择日期`、`开始日期`、`结束日期`。如果客户现场仍看到 `Today`、`Select date`、`Start date`、`End date` 或英文月份/星期，按以下顺序处理：

1. 确认前端镜像或静态资源已经使用最新源码重新构建。
2. 确认 Nginx、CDN、浏览器没有继续缓存旧 `/assets/*.js`。
3. 强制刷新浏览器页面，必要时清理站点缓存后重新登录。
4. 若仍复现，记录当前页面 URL、加载的前端 JS 文件名和截图，交由研发确认是否存在页面级 locale 覆盖。

### 14.3 页面提示无权限

排查顺序：

1. 检查角色是否包含对应权限码。
2. 检查用户是否加入正确用户组。
3. 检查用户组是否关联资源组。
4. 检查资源组是否包含目标实例。
5. 检查查询权限是否存在和未过期。

### 14.4 工单不执行

排查顺序：

1. 检查工单是否审批通过。
2. 检查执行人是否具备执行权限。
3. 检查 `celery_worker` 是否运行。
4. 检查 `execute` 队列是否积压。
5. 检查目标数据库连接是否正常。
6. 查看 Worker 日志和工单执行日志。

### 14.5 查询失败或被拒绝

常见原因：

- SQL 语法或基础语义错误。
- 在线查询不允许该语句类型。
- 用户无在线查询权限。
- 实例不在资源范围内。
- 数据库已停用。
- 查询权限不存在、过期或粒度不匹配。
- 目标数据库账号权限不足。

处理建议：

- 根据页面错误提示定位层级。
- 使用管理员账号检查实例、数据库和查询授权配置。
- 如目标数据库返回错误，按数据库侧错误处理。

### 14.6 敏感配置无法解密

典型原因：

- `SECRET_KEY` 被修改。
- 生产 Secret 被错误覆盖。
- 使用了不匹配的数据库备份和配置文件。

处理：

1. 立即查找旧 `.env` 或旧 Secret。
2. 恢复原 `SECRET_KEY`。
3. 重启服务。
4. 验证实例密码和系统敏感配置可解密。
5. 如无法找回，只能重新录入相关敏感配置。

### 14.7 License 激活失败

排查顺序：

1. 检查客户 ID 是否与授权中心一致。
2. 检查激活码是否属于 Sagitta Control 项目。
3. 检查授权项目码是否为 `sagittadb`。
4. 检查部署指纹是否与授权中心记录一致。
5. 检查授权中心激活码状态是否 active。
6. 检查服务器网络是否可访问授权中心。
7. 检查系统时间是否正确。

### 14.8 在线授权超过宽限期

现象：

- 业务 API 返回 License 无效。
- 授权页仍可访问。

处理：

1. 恢复到授权中心的网络访问。
2. 在授权页执行联网刷新。
3. 如客户长期离线，切换到 challenge-response 离线授权。
4. 确认 `LICENSE_ONLINE_GRACE_DAYS` 符合合同和交付约定。

### 14.9 通知没有送达

排查顺序：

1. 检查通知渠道配置。
2. 检查用户资料中的邮箱或企业 IM 身份。
3. 检查 `notify` 队列。
4. 查看通知投递日志。
5. 检查客户网络是否允许访问邮件或企业 IM API。

### 14.10 观测采集失败

排查顺序：

1. 检查目标实例连接。
2. 检查目标数据库账号权限。
3. 检查采集配置是否启用。
4. 查看 `monitor` 队列和 Worker 日志。
5. 对 Oracle 检查动态性能视图、AWR 或 SQL Monitor 权限。
6. 对 StarRocks、Doris 等检查当前 SQL 活动视图权限。

## 15. 客户交付记录建议

每次客户正式交付建议保存：

- 客户名称和客户 ID。
- Sagitta Control 版本号。
- 部署方式和服务器信息。
- 镜像摘要和客户包 sha256。
- `.env` 配置项摘要，不保存明文密码。
- License 激活方式和授权状态。
- 正式激活部署指纹。
- 首个实例连接测试结果。
- 用户、角色、资源组、审批流配置确认。
- 通知渠道测试结果。
- 验收报告 Markdown/JSON。
- `go-live-check.sh` 输出。
- 数据库备份文件路径。
- 升级和回滚方案。
- 客户联系人、运维责任人和支持渠道。

## 16. 运维交接清单

交接给客户运维团队前确认：

- 客户知道平台访问地址和管理员账号保管方式。
- 客户知道 `.env`、Secret、证书和备份目录位置。
- 客户知道如何查看服务状态和日志。
- 客户知道如何备份和恢复 PostgreSQL。
- 客户知道如何刷新在线 License 或导入离线授权。
- 客户知道如何查看用户、权限、资源组和查询授权。
- 客户知道如何生成诊断包并安全发送给支持团队。
- 客户知道升级前必须备份，回滚前必须判断数据库迁移影响。
- 客户知道 `SECRET_KEY` 不可随意修改。
- 客户知道正式推广前必须执行 go-live 门禁。
