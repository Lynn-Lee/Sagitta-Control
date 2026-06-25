# Sagitta Control 运维升级指南

本文面向客户运维、DBA 和平台管理员，说明 Sagitta Control 的日常巡检、备份、升级、回滚、日志诊断和安全基线。建议把本文和实际部署目录、访问域名、负责人、备份位置一起纳入客户侧运维交接材料。

共享运维截图、日志和诊断包前，请先确认没有暴露服务器 IP、`.env`、License 文件、激活码、数据库密码、Token 或未脱敏客户数据。

## 1. 日常巡检

在部署目录执行：

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

如果 `.env` 修改过端口，请使用实际端口，例如 `BACKEND_PORT=18000`、`FRONTEND_PORT=8080` 时：

```bash
curl -fsS http://127.0.0.1:18000/health
curl -fsS http://127.0.0.1:8080/health
```

每天建议关注：

- `postgres`、`redis`、`backend`、`celery_worker`、`celery_beat`、`frontend` 是否持续运行。
- `License 授权` 页是否显示授权有效或试用有效。
- `商业交付` -> `交付与支持` 是否存在推广、授权、实例或采集阻塞项。
- 数据库实例采集、归档作业和通知任务是否持续失败。
- 服务器磁盘空间、备份目录和日志目录是否接近容量上限。
- 审批、查询和执行任务是否有异常堆积。

产品内巡检建议使用 `商业交付` -> `交付与支持` 汇总推广就绪度、授权状态、客户环境用量、实例接入和监控采集摘要。

![交付与支持巡检入口](../screenshots/23-commercial-support.png)

建议每周至少登录一次 `商业交付` -> `License 授权`，确认在线授权刷新、客户 ID、部署指纹和授权项目状态。

`License 授权` 页面包含客户 ID、部署指纹和授权状态，不作为公开截图素材。对外共享巡检材料时只保留脱敏后的结论，不直接传播授权页原图。

## 2. 备份策略

### 2.1 每次升级前必须备份

在当前部署目录执行：

```bash
mkdir -p backups
timestamp="$(date +%Y%m%d_%H%M%S)"
docker compose exec -T postgres sh -ec \
  'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; pg_dump -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagitta_control}" --no-owner --no-acl --format=plain' \
  | gzip > "backups/sagitta_control_${timestamp}.sql.gz"
```

验证备份文件存在且非空：

```bash
ls -lh "backups/sagitta_control_${timestamp}.sql.gz"
gzip -t "backups/sagitta_control_${timestamp}.sql.gz"
```

### 2.2 同步备份这些材料

- `.env`，尤其是 `SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID`。
- License 文件目录，对应 Docker volume 为 `licenses`。
- 当前部署包目录。
- 客户侧反向代理配置。
- 近期容器日志。
- 客户侧数据库接入账号清单和权限说明。

备份文件包含业务配置和审计数据，应按客户安全规范保存，不要公开流转。

## 3. 升级前检查清单

升级前请确认：

- 已阅读目标版本 Release Notes。
- 已下载新版本部署包和 sha256 文件。
- `sha256sum -c Sagitta-Control-v<version>.zip.sha256` 已通过。
- 已完成 PostgreSQL 备份，并验证 gzip 文件可读。
- 旧版本部署目录、旧版本 zip 和旧版本 `.env` 仍保留。
- 已确认维护窗口、通知范围和回滚负责人。
- 已确认当前系统没有正在执行的 SQL 工单、归档任务或关键审批。
- 已确认新版本镜像可拉取；离线环境已导入新版本镜像 tar 包。

升级时最重要的原则：复用旧 `.env`，不要重新生成 `SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID`。

## 4. 标准升级流程

假设旧版本目录为 `/opt/sagitta-control/Sagitta-Control-v<old_version>`，新版本目录为 `/opt/sagitta-control/Sagitta-Control-v2.3.5`。

解压新版本并复制旧配置：

```bash
cd /opt/sagitta-control
unzip Sagitta-Control-v2.3.5.zip
cd Sagitta-Control-v2.3.5
cp /opt/sagitta-control/Sagitta-Control-v<old_version>/.env .env
```

确认关键配置已继承：

```bash
grep -E '^(SECRET_KEY|LICENSE_CUSTOMER_ID|LICENSE_DEPLOYMENT_ID|BACKEND_PORT|FRONTEND_PORT)=' .env
```

执行升级：

```bash
./upgrade.sh 2.3.5
```

升级脚本会执行：

- 将 `docker-compose.yml` 中后端和前端镜像标签更新为目标版本。
- 拉取固定版本镜像。
- 启动 PostgreSQL 和 Redis。
- 创建 PostgreSQL 备份到 `./backups/`。
- 执行 Alembic 数据库迁移。
- 重建应用服务。
- 检查后端和前端健康状态。

升级后检查：

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

然后登录系统确认：

- 授权状态正常。
- 管理员可以进入 Dashboard。
- 实例列表、SQL 工单、在线查询、查询权限、审计日志可以正常打开。
- `商业交付` -> `交付与支持` 可生成验收报告。

升级后的实例、工单、查询、权限和审计入口属于人工点检项；建议在 `商业交付` -> `交付与支持` 生成验收报告并归档，不在运维指南中混入单个功能页面截图，避免将功能页面误读为升级步骤页面。

## 5. 升级失败时怎么处理

先保留现场，不要立刻删除新版本目录：

```bash
docker compose ps
docker compose logs --tail=200 backend > backend-upgrade-error.log
docker compose logs --tail=200 celery_worker > celery-worker-upgrade-error.log
docker compose logs --tail=200 frontend > frontend-upgrade-error.log
```

按现象定位：

| 现象 | 优先检查 |
|---|---|
| 镜像拉取失败 | GHCR 网络、代理、镜像版本、离线镜像是否已导入。 |
| 数据库备份失败 | `postgres` 是否 healthy、磁盘空间、数据库密码、volume 是否正确。 |
| Alembic 迁移失败 | `backend` 日志、数据库连接、是否跨多个版本跳升、备份是否已完成。 |
| 后端健康失败 | `.env`、PostgreSQL、Redis、License 公钥、商业完整性 Manifest。 |
| 前端健康失败 | `frontend` 容器、`nginx.conf`、后端容器、端口和反向代理。 |

如果失败发生在数据库迁移前，通常可以直接回到旧目录继续运行旧版本。如果失败发生在数据库迁移后，请先评估迁移是否可逆；不确定时联系 Sagitta Control 支持团队后再回滚。

## 6. 回滚流程

回滚前确认：

- 已保留升级失败日志。
- 已确认要恢复的数据库备份文件。
- 已确认旧版本部署目录和旧版本镜像仍可用。
- 已通知业务团队回滚窗口。

示例：从新版本回滚到旧版本。

停止新版本服务：

```bash
cd /opt/sagitta-control/Sagitta-Control-v2.3.5
docker compose down
```

切回旧版本目录并启动基础服务：

```bash
cd /opt/sagitta-control/Sagitta-Control-v<old_version>
docker compose up -d postgres redis
```

恢复升级前数据库备份。备份文件可以来自旧目录手工备份，也可以来自新版本 `upgrade.sh` 生成的 `backups/sagitta_control_<timestamp>.sql.gz`：

```bash
gunzip -c /path/to/sagitta_control_<timestamp>.sql.gz \
  | docker compose exec -T postgres sh -ec \
      'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; psql -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagitta_control}"'
```

启动旧版本服务并检查：

```bash
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

登录后验证授权、实例、SQL 工单、在线查询、查询权限和审计入口。生产回滚前请先评估数据库迁移是否可逆；若不确定，请联系 Sagitta Control 支持团队后再操作。

## 7. 日志和诊断

查看服务日志：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 celery_worker
docker compose logs --tail=200 celery_beat
docker compose logs --tail=200 frontend
```

持续跟踪日志：

```bash
docker compose logs -f backend celery_worker celery_beat
```

在产品内可以打开 `商业交付` -> `交付与支持`：

- 生成 Markdown 或 JSON 验收报告。
- 导出脱敏诊断包。
- 查看推广就绪度。
- 查看授权、实例、用户和监控采集摘要。

提交支持请求时建议提供：

- Sagitta Control 版本号。
- 部署方式：Docker Compose 或 Helm。
- 后端健康接口结果。
- `docker compose ps` 输出。
- 相关容器日志。
- 脱敏诊断包。
- 授权管理页展示的授权项目、客户 ID 和部署指纹后几位。

不要提供 `.env` 明文、License 私钥、激活码、真实数据库密码或未脱敏客户数据。

## 8. 常见故障定位

| 现象 | 优先检查 |
|---|---|
| 前端打不开 | `frontend` 容器、反向代理、端口、防火墙、浏览器控制台。 |
| 后端健康失败 | `backend` 日志、数据库连接、Redis 连接、环境变量。 |
| 任务不执行 | `celery_worker`、`celery_beat` 日志和 Redis 状态。 |
| 授权过期 | 授权中心连通性、服务器时间、客户 ID、部署指纹。 |
| 实例采集失败 | 数据库账号权限、网络连通性、数据库版本和驱动。 |
| 查询无权限 | 用户角色、用户组、资源组、查询权限有效期。 |
| 工单卡住 | 审批流程、审批人、通知配置、Worker 任务状态。 |
| 升级后页面静态资源异常 | 浏览器缓存、前端容器版本、反向代理缓存策略。 |

## 9. 安全基线

生产环境建议：

- 使用 HTTPS 入口。
- 限制后台访问来源。
- 为管理员启用强密码和最小权限。
- 定期轮换数据库接入账号。
- 定期下载并归档审计日志。
- 只使用固定版本镜像，不使用浮动镜像标签。
- 不修改 `SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID`，除非明确执行全新部署。
- 不把部署包、截图、日志和诊断包直接公开到互联网。
- 对包含客户业务信息的审计导出和诊断包执行内部审批。

## 10. 运维交接清单

交付给客户运维团队前，请确认：

- 已记录部署目录、访问域名和负责人。
- 已说明前端和后端端口、反向代理规则和证书位置。
- 已说明备份位置、备份频率和恢复方式。
- 已记录升级脚本、升级窗口和回滚步骤。
- 已说明 License 刷新和离线授权流程。
- 已说明支持请求需要提供的脱敏材料。
- 已说明截图和日志不得暴露服务器 IP、密钥和客户数据。
