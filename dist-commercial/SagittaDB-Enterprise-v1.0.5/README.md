# SagittaDB Enterprise v1.0.5

这是 SagittaDB Enterprise 客户部署包。部署包只包含生产部署配置，应用代码通过固定版本 Docker 镜像交付。

## 镜像

- 后端：`ghcr.io/lynn-lee/sagittadb-backend:1.0.5`
- 前端：`ghcr.io/lynn-lee/sagittadb-frontend:1.0.5`

生产环境不要使用 `latest`，请保留 `docker-compose.yml` 中的明确版本标签。

## 首次部署

```bash
cp .env.example .env
# 编辑 .env，替换所有 CHANGE_ME 值。
docker login ghcr.io
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

前端服务健康后，访问 `http://<server>/`。

## 升级

```bash
./upgrade.sh 1.0.5
```

升级脚本会更新镜像标签、拉取镜像、备份 PostgreSQL、执行 Alembic 迁移并检查前后端健康状态。

## 离线镜像导入

如果服务器无法访问镜像仓库，请导入 SagittaDB 支持团队提供的镜像包：

```bash
docker load < sagittadb-backend-1.0.5.tar
docker load < sagittadb-frontend-1.0.5.tar
docker compose up -d
```

## License

登录后可在授权管理页面导入离线 License，或输入在线激活码完成授权。也可以使用 `verify-license.sh` 验证在线激活和刷新流程：

```bash
./verify-license.sh <activation_code> <customer_id>
```

SagittaDB Enterprise 使用统一授权中心 License-Server-Center。在线激活和联网刷新会由后端自动提交授权项目码 `sagittadb`，授权管理页应显示 `授权项目：SagittaDB（sagittadb）`。

共享日志或配置时，不要打包 License 文件、私钥、激活码或 `.env` 中的敏感值。
