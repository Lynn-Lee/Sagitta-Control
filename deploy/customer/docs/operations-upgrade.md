# SagittaDB Enterprise 运维升级指南

本文面向客户运维、DBA 和平台管理员，说明 SagittaDB Enterprise 的日常巡检、备份、升级、回滚和支持信息收集方式。

## 1. 日常巡检

建议每天检查：

```bash
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

重点关注：

- PostgreSQL、Redis、backend、celery_worker、celery_beat、frontend 是否健康。
- 授权管理页是否显示授权有效或试用有效。
- `商业交付` -> `交付与支持` 中是否存在阻塞项。
- 数据库实例采集、归档作业和通知任务是否有持续失败。
- 服务器磁盘空间、备份目录和日志目录是否接近容量上限。

## 2. 备份

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

备份文件包含业务配置和审计数据，应按客户安全规范保存，不要公开流转。

## 3. 升级

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
- 业务菜单、实例列表、SQL 工单、在线查询、审计日志可以正常打开。
- `商业交付` -> `交付与支持` 可生成验收报告。

## 4. 回滚

如果升级后出现阻塞问题：

1. 保留现场日志和错误截图。
2. 停止当前服务。
3. 切回上一个部署包目录。
4. 恢复升级前数据库备份。
5. 使用上一个版本镜像启动。

示例：

```bash
docker compose down
psql -h 127.0.0.1 -U sagitta -d sagittadb < backups/<backup-file>.sql
cd /path/to/SagittaDB-Enterprise-v<previous_version>
docker compose up -d
```

生产回滚前请先评估数据库迁移是否可逆。若不确定，请联系 SagittaDB 支持团队。

## 5. 日志和诊断

查看服务日志：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 celery_worker
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
- 授权管理页展示的授权项目和客户 ID。

不要提供 `.env` 明文、License 私钥、激活码、真实数据库密码或未脱敏客户数据。

## 6. 安全基线

生产环境建议：

- 使用 HTTPS 入口。
- 限制后台访问来源。
- 为管理员启用强密码和最小权限。
- 定期轮换数据库接入账号。
- 定期下载并归档审计日志。
- 只使用固定版本镜像，不使用浮动镜像标签。
- 不修改 `SECRET_KEY` 和 `LICENSE_DEPLOYMENT_ID`，除非明确执行全新部署。
