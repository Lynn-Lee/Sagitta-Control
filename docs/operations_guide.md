# SagittaDB 运维文档

> 文档版本：v1.0  
> 适用版本：SagittaDB v1.0-GA + v2-lite 授权体系  
> 目标读者：运维工程师、DBA、DevOps、系统管理员

## 1. 运维范围

本文档说明 SagittaDB 正式运行后的部署、初始化、巡检、日志、备份恢复、升级回滚、监控告警、容量管理、故障处理和安全检查。

## 2. 部署与服务清单

### 2.1 推荐部署方式

生产环境推荐使用 Docker Compose 或 Kubernetes + Helm。首次部署前应完成：

- 准备 PostgreSQL、Redis、后端、前端、Worker、Beat 和反向代理运行环境。
- 将 `.env.example` 复制为 `.env`，替换所有默认密码和 `CHANGE_ME` 值。
- 设置 `APP_ENV=production`，并使用 32 位以上随机 `SECRET_KEY`。
- 配置 `LICENSE_PUBLIC_KEY`、`LICENSE_CUSTOMER_ID`、`LICENSE_SERVER_URL` 和稳定的 `LICENSE_DEPLOYMENT_ID`。
- 仅暴露 HTTPS 前端入口，禁止公网直接暴露 PostgreSQL、Redis、Flower、Prometheus、Grafana 和后端调试入口。

Docker Compose 首次部署示例：

```bash
cp .env.example .env
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

Kubernetes 部署时应先更新 Helm values 中的镜像、Secret、域名、证书、资源限制和持久化配置，再执行 `helm upgrade --install`。

### 2.2 Oracle Instant Client

Oracle 11g 或需要 Thick 模式的环境，应在构建后端镜像前准备 Oracle Instant Client。将解压后的客户端目录放入 `backend/vendor/oracle/`，例如 `backend/vendor/oracle/instantclient_19_27/`。后端 Dockerfile 会在构建时把该目录复制到镜像内的 `/opt/oracle/`，检测到 `instantclient_*` 目录后创建 `/opt/oracle/instantclient` 软链接，并刷新系统动态库缓存。

生产环境连接 Oracle 11.2 时，建议设置：

```bash
ORACLE_DRIVER_MODE=thick
```

Linux 容器中通常不需要额外设置 `ORACLE_CLIENT_LIB_DIR`，前提是 Instant Client 已经进入系统动态库搜索路径。如果客户环境不允许把客户端目录放进仓库，可以在自定义后端镜像或宿主机中安装 Instant Client，再通过环境变量和系统库路径暴露给容器。

### 2.3 服务清单

| 服务 | 作用 | 关键风险 |
|---|---|---|
| `frontend` | 前端入口和反向代理。 | 用户无法访问页面或 API 代理异常。 |
| `backend` | FastAPI 后端服务。 | 登录、查询、工单、系统配置不可用。 |
| `celery_worker` | 异步任务执行。 | SQL 执行、通知、归档、采集积压。 |
| `celery_beat` | 定时任务调度。 | 监控采集、周期任务不触发。 |
| `postgres` | 平台元数据。 | 平台核心数据丢失或不可写。 |
| `redis` | Celery broker、Token 黑名单。 | 登录校验 fail-close、任务无法投递。 |
| `flower` | Celery 任务监控。 | 任务排查能力下降。 |
| `prometheus` / `grafana` | 外围监控。 | 无法查看平台和基础设施趋势。 |

## 3. 日常巡检

建议每日执行一次基础巡检，每周执行一次完整巡检。

### 3.1 服务状态

```bash
docker compose -f deploy/docker-compose.yml ps
```

重点检查：

- 所有核心服务为 `Up` 或 `healthy`。
- `backend` 没有频繁重启。
- `celery_worker` 和 `celery_beat` 正常运行。
- `postgres` 和 `redis` 健康。

### 3.2 健康接口

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1/health
```

外部入口通过 HTTPS 验证：

```bash
curl -I https://db.example.com
```

### 3.3 Celery 队列

```bash
docker compose -f deploy/docker-compose.yml exec celery_worker celery -A app.celery_app inspect active
docker compose -f deploy/docker-compose.yml exec celery_worker celery -A app.celery_app inspect reserved
docker compose -f deploy/docker-compose.yml exec celery_worker celery -A app.celery_app inspect scheduled
```

如果任务长期停留在 reserved 或 active，需要检查目标数据库连接、Worker 日志和 Redis 状态。

### 3.4 数据库空间

```bash
docker compose -f deploy/docker-compose.yml exec postgres psql -U sagitta -d sagittadb -c "select pg_size_pretty(pg_database_size('sagittadb'));"
```

重点关注：

- `query_log`、`operation_log`、`notification_delivery_log`、SQL 洞察和会话快照相关表。
- PostgreSQL 数据卷所在磁盘剩余空间。
- 备份目录空间。

## 4. 日志查看

### 4.1 查看服务日志

```bash
docker compose -f deploy/docker-compose.yml logs --tail=200 backend
docker compose -f deploy/docker-compose.yml logs --tail=200 celery_worker
docker compose -f deploy/docker-compose.yml logs --tail=200 celery_beat
docker compose -f deploy/docker-compose.yml logs --tail=200 frontend
```

### 4.2 常见日志关键词

| 关键词 | 含义 |
|---|---|
| `ValueError` | 配置错误、生产安全校验失败或业务参数异常。 |
| `InvalidToken` | JWT、Fernet 或敏感配置解密相关问题。 |
| `Redis` / `Connection refused` | Redis 连接异常，会影响登录黑名单和 Celery。 |
| `OperationalError` | PostgreSQL 或目标数据库连接异常。 |
| `Task failed` | Celery 任务失败，需要结合任务名排查。 |

## 5. 备份与恢复

### 5.1 备份策略

建议：

- 每日全量备份 PostgreSQL。
- 备份保留至少 7 天，生产关键环境建议 30 天。
- 重大升级前执行临时备份。
- 定期抽检恢复，避免“备份存在但不可恢复”。

### 5.2 执行备份

```bash
bash deploy/backup/backup-postgres.sh
```

或使用发布脚本内置备份：

```bash
BACKUP_DIR=/data/sagittadb/backups BACKUP_RETAIN_DAYS=14 bash deploy/update-prod.sh
```

备份完成后检查：

```bash
ls -lh /data/sagittadb/backups
```

### 5.3 恢复数据

恢复前必须确认：

- 已停止写入流量。
- 已备份当前异常现场。
- 已确认目标备份文件完整。

执行恢复：

```bash
bash deploy/backup/restore-postgres.sh
```

恢复后验证：

- 服务可启动。
- 管理员可登录。
- 工单、查询权限、实例、审计日志可查看。
- 随机抽查关键配置和加密字段可正常解密。

## 6. 升级与回滚

### 6.1 升级前检查

- Git 工作区干净。
- 当前版本和目标版本明确。
- 数据库备份完成。
- 目标版本发布说明已阅读。
- 维护窗口已通知用户。
- 已准备回滚版本和备份文件。

### 6.2 标准升级

```bash
bash deploy/update-prod.sh --ref <target_ref>
```

升级后验证：

- `docker compose -f deploy/docker-compose.yml ps` 正常。
- `/health` 正常。
- 前端可登录。
- SQL 工单、在线查询和 Celery 任务正常。
- Alembic 版本为最新。

### 6.3 回滚原则

- 如果只涉及应用异常，优先回滚镜像或 Git tag。
- 如果涉及数据库迁移异常，优先使用升级前备份恢复。
- 不建议在未确认迁移脚本可逆时直接执行 `alembic downgrade`。

## 7. 监控告警

建议监控以下指标：

| 类别 | 指标 |
|---|---|
| 服务 | 容器存活、重启次数、CPU、内存。 |
| 后端 | `/health`、接口错误率、响应时间。 |
| Celery | 队列积压、任务失败、Worker 存活。 |
| PostgreSQL | 连接数、磁盘空间、数据库大小、慢查询。 |
| Redis | 存活、内存、连接数、持久化状态。 |
| 业务 | 工单执行失败、通知失败、归档失败、采集失败。 |

Prometheus 配置位于 `deploy/prometheus/`，Grafana provisioning 位于 `deploy/grafana/provisioning/`。

## 8. 容量管理

### 8.1 易增长数据

| 数据 | 说明 |
|---|---|
| 查询历史 | 在线查询和导出记录。 |
| 操作审计 | 登录、配置、工单和权限操作。 |
| 通知日志 | 主动通知投递记录。 |
| 会话快照 | 周期性会话采样。 |
| SQL 洞察 | SQL 样本、指纹和采集状态。 |
| 归档批次日志 | 归档执行批次、影响行数和异常明细。 |

### 8.2 管理建议

- 对审计和查询历史设置保留周期。
- 定期清理无业务价值的旧诊断采样。
- 监控 PostgreSQL 数据卷使用率。
- 下载文件、导出文件和临时文件建议设置清理任务。

## 9. 常见故障处理

### 9.1 用户无法登录

排查顺序：

1. 检查 `backend` 是否健康。
2. 检查 Redis 是否可用；Token 黑名单校验采用 fail-close。
3. 查看 `backend` 日志是否有密码策略、JWT 或第三方认证错误。
4. 如果是默认密码或过期密码，按页面提示完成强制改密。
5. 第三方登录失败时检查系统配置中的 LDAP/OAuth 参数。

### 9.2 工单一直不执行

排查顺序：

1. 检查工单是否已审批通过。
2. 检查用户是否具备执行权限。
3. 检查 `celery_worker` 是否存活。
4. 查看 `execute` 队列是否积压。
5. 查看目标数据库连接是否异常。
6. 查看 `celery_worker` 日志中的任务异常。

### 9.3 查询被拒绝

常见原因：

- 用户没有 `query_query` 权限。
- 实例不在用户资源组范围内。
- 数据库已停用。
- 查询权限不存在或已过期。
- 表级授权粒度不匹配。

处理方式：

- 使用查询访问检查接口或页面提示定位拒绝层级。
- 调整用户角色、用户组、资源组或查询授权。

### 9.4 敏感配置无法解密

典型原因是 `SECRET_KEY` 被修改。处理方式：

- 立即确认是否存在旧 `.env` 或旧 Secret。
- 恢复原 `SECRET_KEY` 后重启服务。
- 如果无法找回原密钥，需要重新录入实例密码、SSH 密钥和敏感系统配置。

### 9.5 通知没有送达

排查顺序：

1. 检查 `notify` 队列是否正常。
2. 检查系统配置中的邮件、钉钉、飞书、企微参数。
3. 检查用户资料中的 `email`、`dingtalk_user_id`、`feishu_open_id`、`wecom_userid`。
4. 查看 `notification_delivery_log` 中的失败原因。

## 10. 安全运维检查表

每月建议检查：

- 生产环境未使用默认 `SECRET_KEY`。
- PostgreSQL、Redis、Grafana 未使用默认密码。
- 外网未暴露数据库、Redis、Flower、Prometheus 和 Grafana 管理口。
- 管理员账号数量合理，离职账号已禁用。
- 用户角色和用户组资源范围符合最小权限原则。
- 查询权限有效期合理，无长期不必要授权。
- 审批流责任人仍然有效。
- 备份文件可恢复，且权限受控。
- 第三方认证和通知密钥未过期。
- 系统日志无持续重复错误。

发布、升级或客户验收前建议额外执行：

```bash
deploy/preflight-check.sh
scripts/ga-acceptance-check.py --base-url http://127.0.0.1:8000 \
  --username <admin> --password '<password>'
```

也可使用 `--token '<access_token>'` 代替用户名密码。默认模式只做非破坏性检查；提供 `--instance-id <id> --db-name <db>` 后，会额外检查 SQL 工单风险预案、在线查询权限排查、查询权限风险预案和数据字典注册库列表。真实创建类验收必须显式加 `--submit-workflow`、`--apply-query-privilege`、`--submit-archive`，License 和通知验收分别使用 `--activate-license`、`--refresh-license`、`--notify-user-id <id>`。

上线和升级前应保存以下内部记录：服务版本、镜像摘要、数据库备份文件、健康检查结果、关键链路验收结果、安全扫描结果和 License 激活/刷新结果。
