# Deploy — 部署配置目录

## 快速参考

| 场景 | 使用文件 | 详细文档 |
|---|---|---|
| **本地开发 / 功能测试** | 根目录 `docker-compose.yml` | [docs/deploy_test_env.md](../docs/deploy_test_env.md) |
| **生产环境部署** | `deploy/docker-compose.yml`（本目录） | [docs/deploy_production_env.md](../docs/deploy_production_env.md) |

## 两套 Compose 文件的区别

| 配置项 | 开发（根目录） | 生产（deploy/） |
|---|---|---|
| 代码挂载 | `./backend:/app`（热重载） | 无（使用镜像内置代码） |
| uvicorn workers | 1（--reload） | 4 |
| Celery 并发 | 4 | 8 |
| 资源限制 | 无 | 有（CPU/内存 limit） |
| restart 策略 | `unless-stopped` | `always` |
| Grafana SSO | 关闭 | 启用（OAuth 集成） |

## Oracle 11g 额外要求

如果生产环境需要连接 `Oracle 11.2` 或更早版本：

- 请启用 `.env` 中的 `ORACLE_DRIVER_MODE=thick`
- 请在构建镜像前把 Oracle Instant Client 解压到 `backend/vendor/oracle/instantclient_*`
- 然后重新执行 `docker compose -f deploy/docker-compose.yml build backend celery_worker celery_beat flower`

原因：

- `python-oracledb` 的默认 Thin 模式只能直连 Oracle `12.1+`
- 连接 Oracle `11.2` 需要 Thick 模式和 Oracle Instant Client

## 目录结构

```
deploy/
├── docker-compose.yml      # 生产部署（独立完整，不依赖根目录文件）
├── nginx.conf              # Nginx 反向代理配置
├── prometheus/
│   ├── prometheus.yml      # Prometheus 采集配置
│   ├── alertmanager.yml    # 告警路由配置
│   └── rules/
│       └── db_alerts.yml   # 默认告警规则
├── grafana/
│   └── provisioning/       # Grafana 预置 Dashboard
├── helm/
│   └── sagittadb/          # K8s Helm Chart（生产 K8s 部署）
└── backup/
    ├── backup-postgres.sh  # PostgreSQL 备份脚本
    └── restore-postgres.sh # PostgreSQL 恢复脚本
```
