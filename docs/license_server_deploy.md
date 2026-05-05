# SagittaDB License Server 部署说明

License Server 是商业运营内部服务，负责签发 License、管理客户与激活码，并提供简易 Web 管理界面。不要把该服务部署到客户环境。

源码位于私有仓库：

```text
https://github.com/Lynn-Lee/SagittaDB-License-Server
```

SagittaDB 产品镜像只包含公钥验签逻辑和在线激活客户端，不包含 License Server 源码或私钥。

## 环境变量

```bash
LICENSE_DB_PASSWORD=<强密码>
LICENSE_AUTHORITY_ADMIN_TOKEN=<管理端 Bearer Token>
SAGITTADB_LICENSE_PRIVATE_KEY=<Ed25519 private key>
LICENSE_ADMIN_PATH=/<隐藏管理路径>
LICENSE_SERVER_PORT=8011
```

生成密钥对：

```bash
cd backend
./.venv/bin/python ../tools/license_issue.py --generate-keypair
```

在 SagittaDB 客户或内部验证环境中配置 `LICENSE_PUBLIC_KEY`；`SAGITTADB_LICENSE_PRIVATE_KEY` 只允许保存在内部 License Server 上。

## VPS 部署

```bash
mkdir -p /opt/sagittadb-license-server
cd /opt/sagittadb-license-server
docker compose up -d
```

生产环境中容器默认只监听 `127.0.0.1:8011`，由 Nginx/Xray 对外发布 HTTPS 入口：

```text
https://sagitta.loveai.asia
```

打开 `https://sagitta.loveai.asia/<隐藏管理路径>`，输入管理 Token 后依次创建：

1. 客户
2. 激活码
3. 在 SagittaDB 产品 License 页面执行在线激活

## 备份

定期备份 PostgreSQL 数据库：

```bash
docker compose exec license_postgres pg_dump -U license sagittadb_license > license-server-$(date +%F).sql
```

## 内部生产验证

1. 在 VPS 上启动 License Server。
2. 在一个内部 SagittaDB 环境中配置：
   - `LICENSE_PUBLIC_KEY`
   - `LICENSE_CUSTOMER_ID`
   - `LICENSE_SERVER_URL=https://sagitta.loveai.asia`
   - `LICENSE_SERVER_TOKEN`，仅在边缘代理对产品接口注入或要求 Bearer Token 时配置。
   - `LICENSE_DEPLOYMENT_ID`，首次部署时生成，后续升级保持不变。
3. 在 License Server Web 管理端创建客户和激活码。
4. 在 SagittaDB「系统管理 -> License」页面完成在线激活。
5. 执行 `deploy/customer/verify-license.sh <activation-code> <customer-id>`。
6. 在不同部署指纹的环境中尝试复用同一激活码，应被拒绝。
7. 在 License Server 中挂起激活码，再触发 SagittaDB License 刷新，核心 API 应被阻断。
8. 将激活码恢复为 active 或创建新激活码，再次激活后确认核心 API 恢复。

## 最新剩余计划任务

统一任务清单见 `docs/remaining_plan.md`。License Server 部署侧剩余任务仅保留生产验证、基础备份恢复和运营审计确认；告警增强、部署 ID 遗失支持流程和运营报表不再作为后续研发任务。
