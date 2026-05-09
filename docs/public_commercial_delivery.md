# SagittaDB Public Commercial Delivery

本文档定义 SagittaDB Enterprise 的公开商业交付方式：公开部署包和商业镜像，源码、签发工具、私钥和内部构建流程继续保留在私有仓库。

## 1. Delivery Model

SagittaDB 采用以下边界：

- Public delivery repository：只放产品介绍、部署文件、Helm Chart、安装脚本、法律提示、截图和 Release 下载资产。
- Public container registry：公开拉取固定版本商业镜像。
- Private source repository：继续保留后端源码、前端源码、商业镜像构建脚本、License 签发工具、Manifest 签名工具和内部发布记录。
- License-Server-Center：统一负责在线激活、联网刷新和商业授权状态管理。

推荐 public 仓库结构：

```text
products/
  sagittadb/
    README.md
    docker-compose.yml
    .env.example
    LEGAL-NOTICE.md
    nginx.conf
    helm/
      sagittadb/
    scripts/
      upgrade.sh
      verify-license.sh
    screenshots/
shared/
  legal/
  docs/
README.md
```

当前私有仓库中的 `backend/`、`frontend/`、`tools/license_issue.py`、`tools/license_authority.py`、`tools/sign_manifest.py`、`scripts/build-commercial-images.sh`、`scripts/sign-commercial-artifacts.sh` 不进入 public 仓库。

## 2. Public Repository Content

`products/sagittadb/README.md` 应作为用户入口，包含：

- SagittaDB Enterprise 产品定位和核心功能。
- Docker Compose 快速开始。
- Kubernetes / Helm 部署入口。
- 30 天试用说明。
- 在线激活和离线 challenge-response 简述。
- 商业授权联系方式。
- Release 下载和 sha256 校验方式。

public 仓库可以包含部署资产和截图，但不得包含：

- 后端或前端源码目录。
- `LICENSE_PRIVATE_KEY`、`MANIFEST_PRIVATE_KEY` 或任何私钥材料。
- 授权中心后台 token、真实客户 License、真实激活码、真实 `.env`。
- sourcemap、构建缓存、CI 安全扫描原始报告或内部验收记录。
- `latest` 镜像标签、源码 `build:` 配置或本地源码挂载路径。

## 3. Image Naming

SagittaDB 镜像统一发布到公开 GHCR organization，并只在部署包中引用完整版本号：

```text
ghcr.io/<org>/sagittadb-backend:1.0.5
ghcr.io/<org>/sagittadb-frontend:1.0.5
```

发布规则：

- 镜像允许匿名公开拉取。
- 不发布 `latest`，也不在客户部署包中使用浮动标签。
- 后端商业镜像使用 `backend/Dockerfile.commercial`，核心 Python 模块由 Nuitka 编译。
- 前端镜像只包含 build 产物，构建后必须拒绝 `.map` sourcemap。
- 商业镜像默认启用 Manifest 完整性校验。

## 4. GitHub Release

SagittaDB 在统一 public 仓库中按产品独立发版：

```text
Tag: sagittadb/v1.0.5
Title: SagittaDB Enterprise v1.0.5
Assets:
  SagittaDB-Enterprise-v1.0.5.zip
  SagittaDB-Enterprise-v1.0.5.zip.sha256
```

Release notes 使用 [SagittaDB public release template](release_templates/sagittadb_public_release.md)。

用户安装命令示例：

```bash
wget https://github.com/<org>/<public-repo>/releases/download/sagittadb/v1.0.5/SagittaDB-Enterprise-v1.0.5.zip
unzip SagittaDB-Enterprise-v1.0.5.zip
cd SagittaDB-Enterprise-v1.0.5

cp .env.example .env
vim .env

docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

## 5. License Policy

SagittaDB 固定授权项目码：

```text
project=sagittadb
product=sagittadb
```

客户端必须校验：

- License 文档包含 `payload` 和 `signature`。
- `LICENSE_PUBLIC_KEY` 可以验证 Ed25519 签名。
- `project` 或兼容字段 `product` 等于 `sagittadb`。
- `deployment_fingerprint` 如存在，必须匹配当前部署。
- `not_before`、`expires_at`、签名、客户标识和项目码均有效。

试用规则：

- 首次部署没有 License 时自动创建 trial 记录。
- 默认 `LICENSE_TRIAL_DAYS=30`。
- 试用期内全部受保护功能可用。
- 试用期结束后，业务 API 返回 `LICENSE_REQUIRED`，登录、健康检查和授权管理入口继续可用。

## 6. Activation Flows

在线激活：

```text
POST /api/v1/licenses/activate
payload:
  activation_code
  customer_id
  deployment_fingerprint
  project=sagittadb
  product=sagittadb
```

联网刷新：

```text
POST /api/v1/licenses/refresh
payload:
  activation_id
  license_id
  customer_id
  deployment_fingerprint
  project=sagittadb
  product=sagittadb
```

离线授权：

1. 客户在授权管理页生成 Challenge。
2. 客户把 Challenge 发送给 SagittaDB 商业支持。
3. 私有仓库使用 `tools/license_issue.py --challenge-file ... --response-out ...` 签发 response。
4. 客户导入 challenge-response 文件。
5. SagittaDB 校验 Challenge、License 签名、客户 ID、项目码和部署指纹。

生产环境保持：

```text
LICENSE_ALLOW_LEGACY_LICENSE_IMPORT=false
```

## 7. Private Release Flow

私有仓库负责生成 public 交付资产：

1. 确认版本号，例如 `1.0.5`。
2. 构建并推送 `ghcr.io/<org>/sagittadb-backend:1.0.5`。
3. 构建并推送 `ghcr.io/<org>/sagittadb-frontend:1.0.5`。
4. 生成并签名商业 Manifest。
5. 渲染客户部署包。
6. 生成 zip 和 sha256。
7. 检查部署包无源码、私钥、token、真实 License、sourcemap 和浮动镜像标签。
8. 同步部署文件到 public 仓库 `products/sagittadb/`。
9. 在 public 仓库创建 `sagittadb/v1.0.5` Release。
10. 上传 zip 和 sha256。

自动发布由 `.github/workflows/commercial-release.yml` 执行：

- 推送到 `main` 或 `release/**` 时，生成快照版本，例如 `1.0.5-dev.123.abcdef0`，并同步到 `Public-Releases`。
- 推送正式 tag `vX.Y.Z` 时，生成正式版本 `X.Y.Z`。
- 手动触发 workflow 时，如果填写 `version`，生成指定正式版本；如果留空，生成快照版本。
- workflow 会推送公开镜像到 `ghcr.io/lynn-lee/sagittadb-backend:<version>` 和 `ghcr.io/lynn-lee/sagittadb-frontend:<version>`。
- workflow 会更新 `Lynn-Lee/Public-Releases` 的 `products/sagittadb/`，并把 zip/sha256 放入 `products/sagittadb/releases/v<version>/`。

私有仓库需要配置 GitHub Secrets：

```text
MANIFEST_PRIVATE_KEY
PUBLIC_RELEASES_TOKEN
```

`MANIFEST_PRIVATE_KEY` 用于商业镜像 Manifest 签名。`PUBLIC_RELEASES_TOKEN` 必须是可写 `Lynn-Lee/Public-Releases` 的 GitHub token，建议只授予该 public 仓库的 contents read/write 权限。

现有脚本入口：

```bash
VERSION=1.0.5 \
IMAGE_REPOSITORY=ghcr.io/<org>/sagittadb \
MANIFEST_PRIVATE_KEY_FILE=/path/to/manifest_private_key \
./scripts/build-commercial-images.sh

python scripts/render-customer-package.py \
  --version 1.0.5 \
  --image-repository ghcr.io/<org>/sagittadb \
  --output-dir dist-commercial \
  --package-name SagittaDB-Enterprise-v1.0.5
```

## 8. Acceptance Checklist

每个 public commercial release 必须满足：

- public Release 可下载 `SagittaDB-Enterprise-vX.Y.Z.zip` 和 `.sha256`。
- GHCR 镜像可匿名拉取。
- 部署包不需要源码即可启动。
- `docker-compose.yml` 和 Helm values 使用固定版本镜像。
- 首次部署自动进入 30 天全功能试用。
- 试用到期后业务功能阻断，授权管理入口仍可访问。
- 在线激活、联网刷新和离线 challenge-response 均可用。
- License 项目码必须是 `sagittadb`。
- 篡改商业镜像关键文件时完整性校验失败。
- public 仓库和 Release 包不包含源码、私钥、token、真实 License、sourcemap 或 `latest` 标签。

## 9. Recommended Defaults

```text
Product Code: sagittadb
Product Name: SagittaDB
Edition: enterprise
Trial Days: 30
Release Tag: sagittadb/v1.0.5
Package Name: SagittaDB-Enterprise-v1.0.5.zip
Backend Image: ghcr.io/<org>/sagittadb-backend:1.0.5
Frontend Image: ghcr.io/<org>/sagittadb-frontend:1.0.5
License Server: License-Server-Center
Expired Behavior: login and license management remain available; business APIs are blocked
```
