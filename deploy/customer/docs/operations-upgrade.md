# SagittaDB Enterprise 运维升级指南

本文面向客户运维、DBA 和平台管理员，说明 SagittaDB Enterprise 的日常巡检、备份、升级、回滚、日志诊断和安全基线。

共享运维截图、日志和诊断包前，请先确认没有暴露服务器 IP、`.env`、License 文件、激活码、数据库密码或未脱敏客户数据。

## 1. 日常巡检

建议每天检查服务状态：

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

重点关注：

- PostgreSQL、Redis、backend、celery_worker、celery_beat、frontend 是否健康。
- `License 授权` 页是否显示授权有效或试用有效。
- `商业交付` -> `交付与支持` 中是否存在阻塞项。
- 数据库实例采集、归档作业和通知任务是否持续失败。
- 服务器磁盘空间、备份目录和日志目录是否接近容量上限。
- 审批、查询和执行任务是否有异常堆积。

产品内巡检建议使用 `商业交付` -> `交付与支持` 汇总推广就绪度、授权状态、客户环境用量、实例接入和监控采集摘要。

![交付与支持巡检入口](../screenshots/23-commercial-support.png)

建议每周至少登录一次 `商业交付` -> `License 授权`，确认在线授权刷新、客户 ID、部署指纹和授权项目状态。

`License 授权` 页面包含客户 ID、部署指纹和授权状态，不作为公开截图素材。对外共享巡检材料时只保留脱敏后的结论，不直接传播授权页原图。

## 2. 备份策略

升级、迁移或重大配置调整前必须备份 PostgreSQL 数据：

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-sagitta}" \
  "${POSTGRES_DB:-sagittadb}" \
  > "backups/sagittadb-$(date +%Y%m%d-%H%M%S).sql"
```

同时建议备份：

- `.env`。
- License 文件目录。
- 客户侧反向代理配置。
- 当前部署包目录。
- 近期容器日志。
- 客户侧数据库接入账号清单和权限说明。

备份文件包含业务配置和审计数据，应按客户安全规范保存，不要公开流转。

## 3. 升级流程

升级前请确认：

- 已阅读目标版本 Release Notes。
- 已下载新版本部署包和 sha256 文件。
- 已校验部署包 sha256。
- 已完成 PostgreSQL 备份。
- 已确认可用维护窗口。
- 已确认回滚路径和上一版本部署包仍可用。

将新版本部署包解压到新目录后执行：

```bash
cd SagittaDB-Enterprise-v__SAGITTADB_VERSION__
cp /path/to/old/.env .env
./upgrade.sh __SAGITTADB_VERSION__
```

升级脚本会执行：

- 拉取固定版本镜像。
- 备份 PostgreSQL。
- 执行 Alembic 数据库迁移。
- 重启服务。
- 检查前后端健康状态。

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

## 4. 回滚流程

如果升级后出现阻塞问题：

1. 保留现场日志和错误截图。
2. 停止当前服务。
3. 切回上一个部署包目录。
4. 恢复升级前数据库备份。
5. 使用上一个版本镜像启动。
6. 登录后验证授权、实例、工单、查询和审计入口。

示例：

```bash
docker compose down
psql -h 127.0.0.1 -U sagitta -d sagittadb < backups/<backup-file>.sql
cd /path/to/SagittaDB-Enterprise-v<previous_version>
docker compose up -d
```

生产回滚前请先评估数据库迁移是否可逆。若不确定，请联系 SagittaDB 支持团队后再操作。

## 5. 日志和诊断

查看服务日志：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 celery_worker
docker compose logs --tail=200 celery_beat
docker compose logs --tail=200 frontend
```

在产品内可以打开 `商业交付` -> `交付与支持`：

- 生成 Markdown 或 JSON 验收报告。
- 导出脱敏诊断包。
- 查看推广就绪度。
- 查看授权、实例、用户和监控采集摘要。

提交支持请求时建议提供：

- SagittaDB 版本号。
- 部署方式：Docker Compose 或 Helm。
- 后端健康接口结果。
- 相关容器日志。
- 脱敏诊断包。
- 授权管理页展示的授权项目、客户 ID 和部署指纹后几位。

不要提供 `.env` 明文、License 私钥、激活码、真实数据库密码或未脱敏客户数据。

## 6. 常见故障定位

| 现象 | 优先检查 |
|---|---|
| 前端打不开 | `frontend` 容器、反向代理、端口、防火墙、浏览器控制台。 |
| 后端健康失败 | `backend` 日志、数据库连接、Redis 连接、环境变量。 |
| 任务不执行 | `celery_worker`、`celery_beat` 日志和 Redis 状态。 |
| 授权过期 | 授权中心连通性、服务器时间、客户 ID、部署指纹。 |
| 实例采集失败 | 数据库账号权限、网络连通性、数据库版本和驱动。 |
| 查询无权限 | 用户角色、用户组、资源组、查询权限有效期。 |
| 工单卡住 | 审批流程、审批人、通知配置、Worker 任务状态。 |

## 7. 安全基线

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

## 8. 运维交接清单

交付给客户运维团队前，请确认：

- 已记录部署目录、访问域名和负责人。
- 已说明备份位置、备份频率和恢复方式。
- 已记录升级脚本和回滚步骤。
- 已说明 License 刷新和离线授权流程。
- 已说明支持请求需要提供的脱敏材料。
- 已说明截图和日志不得暴露服务器 IP、密钥和客户数据。
