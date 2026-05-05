# SagittaDB Enterprise v__SAGITTADB_VERSION__

这是 SagittaDB Enterprise 的客户部署包。部署包只包含部署配置；应用代码通过带版本号的 Docker 镜像交付。

## 镜像

- 后端：`__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- 前端：`__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`

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

在线升级：

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

手工升级时，先更新 `docker-compose.yml` 中的镜像标签，再执行：

```bash
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
curl -fsS http://127.0.0.1:8000/health
```

## 离线镜像导入

如果服务器无法访问镜像仓库，请导入 SagittaDB 支持团队提供的镜像包：

```bash
docker load < sagittadb-backend-__SAGITTADB_VERSION__.tar
docker load < sagittadb-frontend-__SAGITTADB_VERSION__.tar
docker compose up -d
```

## License

登录后在 SagittaDB 系统管理页面导入 License 文件，或输入在线激活码完成授权。共享日志或配置时，请不要把 License 文件一并打包。

## 最新剩余计划任务

统一任务清单见 [../../docs/remaining_plan.md](../../docs/remaining_plan.md)。客户部署包交付前必须完成 P0 发布闸门，确认镜像标签固定、License 私钥未包含在包内，并完成升级回滚与授权验证。
