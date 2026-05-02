# SagittaDB 商业版本发布流程

SagittaDB 采用三条线的发布模型：

- `main`：内部源码开发线，不作为客户生产版本来源。
- `release/<major.minor>`：稳定商业交付线，用于构建客户镜像。
- `hotfix/<major.minor.patch>`：从对应 release 线切出的紧急修复分支。

客户只接收带明确版本号的 Docker 镜像和生成好的客户部署包，不接收源码分支。

## 常规发布

```bash
bash scripts/create-release-branch.sh 1.0
git push -u origin release/1.0
git tag v1.0.0
git push origin v1.0.0
```

推送 `v1.0.0` 标签后会触发商业发布流水线，并生成：

- `ghcr.io/<org>/<repo>-backend:1.0.0`
- `ghcr.io/<org>/<repo>-backend:1.0`
- `ghcr.io/<org>/<repo>-frontend:1.0.0`
- `ghcr.io/<org>/<repo>-frontend:1.0`
- `SagittaDB-Enterprise-v1.0.0.zip`

## main 开发镜像

每次推送 `main` 都会发布开发镜像：

- `main-latest`
- `main-<sha>`

这些标签仅供内部验证使用，禁止用于客户生产环境。

## Release 候选镜像

每次推送 `release/1.0` 都会发布候选镜像：

- `release-1.0`
- `release-1.0-<sha>`

这些镜像只用于内部验证或客户预发布验证。

## 热修复

```bash
bash scripts/start-hotfix.sh 1.0.4
# 修复、测试、提交
bash scripts/finish-hotfix.sh 1.0.4
git push origin release/1.0
git push origin main
git push origin v1.0.4
```

推送版本标签后会构建最终客户镜像和部署包。

## 客户交付

向客户交付生成的 `SagittaDB-Enterprise-v<version>.zip`，同时提供匹配的离线 License 文件或在线激活码。部署包内的 `docker-compose.yml` 会固定精确镜像版本，客户环境不应使用 `latest`。

在线激活和续期流程见 `docs/license_operations_v2.md`。License Server 维护在独立私有仓库 `https://github.com/Lynn-Lee/SagittaDB-License-Server`，与客户侧 SagittaDB 镜像分开部署，部署细节见 `docs/license_server_deploy.md`。客户只接收 SagittaDB 部署包、激活码或离线 License 文件。

客户通过以下命令升级：

```bash
./upgrade.sh <new-version>
```
