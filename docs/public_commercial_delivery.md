# Sagitta Control 公开商业交付说明

本文档定义 Sagitta Control 的公开商业交付方式：公开部署包和商业镜像，源码、签发工具、私钥和内部构建流程继续保留在私有仓库。

## 1. 交付模型

Sagitta Control 采用以下边界：

- 公开交付仓库：`Lynn-Lee/Sagitta-Deploy` 是 Sagitta Control 的专用公开交付仓库；根 `README.md` 直接作为用户入口，发布流程会更新仓库根目录下的产品介绍、部署文件、Helm Chart、安装脚本、法律提示、用户手册、运维升级文档、截图和 Release 下载资产。
- 公开镜像仓库：公开拉取固定版本商业镜像。
- 私有源码仓库：继续保留后端源码、前端源码、商业镜像构建脚本、License 签发工具、Manifest 签名工具和内部发布记录。
- License-Server-Center：统一负责在线激活、联网刷新和商业授权状态管理。

推荐公开仓库结构：

```text
README.md
docker-compose.yml
.env.example
LEGAL-NOTICE.md
nginx.conf
prepare-go-live-env.sh
go-live-check.sh
upgrade.sh
verify-license.sh
helm/
  sagitta-control/
docs/
  installation.md
  operations-upgrade.md
  product-manual.md
screenshots/
  02-dashboard-query.png
  09-query-workbench.png
  23-commercial-support.png
  24-audit-log.png
releases/
  v2.3.5/
    Sagitta-Control-v2.3.5.zip
    Sagitta-Control-v2.3.5.zip.sha256
    Sagitta-Control-v2.3.5.zip.sig.json
```

公开仓库根 `README.md` 由 Sagitta Control 私有源码仓库的商业发布 workflow 渲染生成，是客户下载、安装、授权和运维文档的第一入口。

当前私有仓库中的 `backend/`、`frontend/`、`tools/license_issue.py`、`tools/license_authority.py`、`tools/sign_manifest.py`、`scripts/build-commercial-images.sh`、`scripts/sign-commercial-artifacts.sh` 不进入公开仓库。

## 2. 公开仓库内容

公开仓库根 `README.md` 应作为用户入口，包含：

- Sagitta Control 产品定位和核心功能。
- 测试环境页面截图，展示 Dashboard、实例、SQL 工单、在线查询、字典、脱敏、监控、归档、权限、系统配置和审计等核心界面。
- Docker Compose 快速开始。
- Kubernetes / Helm 部署入口。
- 60 天试用说明。
- 在线激活和离线 challenge-response 简述。
- 输入客户 ID 生成正式激活部署指纹的授权操作说明。
- 安装部署、运维升级、产品使用手册入口；客户包内也必须包含 `screenshots/`，保证下载 zip 后 README 和手册中的图片仍可打开。
- 商业授权联系方式。
- Release 下载和 sha256 校验方式。

公开仓库可以包含部署资产和截图，但不得包含：

- 后端或前端源码目录。
- `LICENSE_PRIVATE_KEY`、`MANIFEST_PRIVATE_KEY` 或任何私钥材料。
- 授权中心后台 token、真实客户 License、真实激活码、真实 `.env`。
- sourcemap、构建缓存、CI 安全扫描原始报告或内部验收记录。
- `latest` 镜像标签、源码 `build:` 配置或本地源码挂载路径。
- 真实客户 ID、真实域名、公网 IP、部署指纹、实例名称、账号、客户现场截图、
  支持群截图或授权状态流转记录。
- `License 授权` / `授权管理` 页面原图；该页面包含客户 ID、部署指纹和授权状态，只能在脱敏后的内部支持材料中使用。

公开文档、Release 说明、PR 描述和截图默认使用 `<customer_id>`、`<domain>`、
`<origin-ip>`、`<fingerprint>` 等占位符。客户案例进入公开材料前必须先改写为
通用模板，只保留问题类型、排障步骤和可复用结论。

## 3. 镜像命名

Sagitta Control 镜像发布到公开 GHCR 仓库，并只在部署包中引用完整版本号：

```text
ghcr.io/<org>/sagitta-control-backend:2.3.5
ghcr.io/<org>/sagitta-control-frontend:2.3.5
```

发布规则：

- 镜像允许匿名公开拉取。
- 不发布 `latest`，也不在客户部署包中使用浮动标签。
- 后端商业镜像使用 `backend/Dockerfile.commercial`，默认将 `app/**/*.py` 中除 `__init__.py` 外的应用模块全部由 Nuitka 编译成扩展模块。
- 商业后端镜像构建阶段必须执行源码残留门禁，`/app/app` 下不得存在非白名单 `.py`、`.pyc` 或 `.pyo`。
- 商业根上下文构建必须通过 `.dockerignore` 门禁，禁止将虚拟环境、测试目录、前端依赖、`dist-commercial`、私钥、License 文件或激活材料送入 Docker build context。
- 前端镜像只包含 build 产物，构建后必须拒绝 `.map` sourcemap 和 `sourceMappingURL` 引用，并使用生产压缩/混淆配置。
- 商业镜像默认启用 Manifest 完整性校验；商业构建标识 `SAGITTA_CONTROL_COMMERCIAL_BUILD=true` 时，即使客户把 `APP_INTEGRITY_REQUIRED` 设为 false，启动也必须校验 Manifest。
- 客户部署模板默认启用容器只读根文件系统、`no-new-privileges`、最小能力集和临时目录挂载，降低本地运行态篡改面；前端 Nginx 仅保留绑定 80 端口及启动运行所需的 `NET_BIND_SERVICE`、`CHOWN`、`SETGID`、`SETUID`。

## 4. GitHub Release 规则

Sagitta Control 在专用公开仓库中按版本发版：

```text
Repository: Lynn-Lee/Sagitta-Deploy
Tag: v2.3.5
Title: Sagitta Control v2.3.5
Assets:
  Sagitta-Control-v2.3.5.zip
  Sagitta-Control-v2.3.5.zip.sha256
```

Release 发布说明使用 [Sagitta Control 公开发布模板](release_templates/sagitta_control_public_release.md)。

用户安装命令示例：

```bash
wget https://github.com/Lynn-Lee/Sagitta-Deploy/releases/download/v2.3.5/Sagitta-Control-v2.3.5.zip
wget https://github.com/Lynn-Lee/Sagitta-Deploy/releases/download/v2.3.5/Sagitta-Control-v2.3.5.zip.sha256
sha256sum -c Sagitta-Control-v2.3.5.zip.sha256
unzip Sagitta-Control-v2.3.5.zip
cd Sagitta-Control-v2.3.5

cp .env.example .env
vim .env

docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

## 5. License 策略

Sagitta Control 固定授权项目码：

```text
project=sagitta-control
product=sagitta-control
```

客户端必须校验：

- License 文档包含 `payload` 和 `signature`。
- `LICENSE_PUBLIC_KEY` 可以验证 Ed25519 签名。
- `project` 或兼容字段 `product` 等于 `sagitta-control`。
- `deployment_fingerprint` 如存在，必须匹配当前部署。
- `not_before`、`expires_at`、签名、客户标识和项目码均有效。

试用规则：

- 首次部署没有 License 时自动创建 trial 记录。
- 默认 `LICENSE_TRIAL_DAYS=60`。
- 试用期内全部受保护功能可用。
- 试用期结束后，业务 API 返回 `LICENSE_REQUIRED`，登录、健康检查和授权管理入口继续可用。
- 在线授权默认 `LICENSE_ONLINE_GRACE_DAYS=7`，每次成功激活或刷新都会更新本地联网校验时间；超过宽限期未成功回源时，在线授权状态转为无效，业务 API 暂停。
- 长期离线客户必须使用 challenge-response 离线授权，离线授权仍按签发 License 的 `expires_at` 和部署指纹校验。

## 6. 授权流程

在线激活：

```text
GET /api/v1/system/license/deployment-fingerprint?customer_id=<customer_id>
response:
  project=sagitta-control
  product=sagitta-control
  customer_id
  deployment_fingerprint

POST /api/v1/licenses/activate
payload:
  activation_code
  customer_id
  deployment_fingerprint
  project=sagitta-control
  product=sagitta-control
```

授权管理页在在线激活区域输入客户 ID 后，会调用部署指纹预览接口生成正式激活部署指纹。运营侧应在用户授权中心录入该指纹，再生成并交付激活码。复制指纹时，HTTPS 站点使用浏览器剪贴板 API，HTTP 试用部署自动降级到兼容复制方式。

联网刷新：

```text
POST /api/v1/licenses/refresh
payload:
  activation_id
  license_id
  customer_id
  deployment_fingerprint
  project=sagitta-control
  product=sagitta-control
```

离线授权：

1. 客户在授权管理页生成 Challenge。
2. 客户把 Challenge 发送给 Sagitta Control 商业支持。
3. 私有仓库使用 `tools/license_issue.py --challenge-file ... --response-out ...` 签发 response。
4. 客户导入 challenge-response 文件。
5. Sagitta Control 校验 Challenge、License 签名、客户 ID、项目码和部署指纹。

生产环境保持：

```text
LICENSE_ALLOW_LEGACY_LICENSE_IMPORT=false
```

## 7. 私有仓库发布流程

私有仓库负责生成公开交付资产：

1. 确认版本号，例如 `2.3.5`。
2. 构建并推送 `ghcr.io/<org>/sagitta-control-backend:2.3.5`。
3. 构建并推送 `ghcr.io/<org>/sagitta-control-frontend:2.3.5`。
4. 生成并签名商业 Manifest。
5. 渲染客户部署包。
6. 生成 zip 和 sha256。
7. 检查部署包无源码、私钥、token、真实 License、sourcemap 和浮动镜像标签。
8. 检查商业后端镜像无应用源码残留：除 `__init__.py` 外，`/app/app` 下不得存在 `.py`、`.pyc` 或 `.pyo`。
9. 检查商业构建上下文 `.dockerignore`，确认 `.venv`、测试目录、依赖缓存、`dist-commercial`、私钥和 License 文件不会进入 Docker context。
10. 生成前后端镜像 CycloneDX SBOM，签名前后端镜像、SBOM 和客户部署包。
11. 执行 `scripts/validate-commercial-release-materials.sh`，确认 zip、sha256、客户包签名、前后端 SBOM、SBOM sha256 和 cosign bundle 均已生成且可校验。
12. 同步部署文件到公开仓库 `Lynn-Lee/Sagitta-Deploy` 根目录。
13. 在公开仓库创建或更新 `v2.3.5` Release。
14. 上传 zip、sha256、签名文件和 SBOM。

源码 CI 和商业发布机制与 DataFusionX 保持一致：

- 推送到 `main` 时，只触发 `.github/workflows/ci.yml` 和 `.github/workflows/release-version-record.yml`，用于源码构建校验和版本记录，不构建或发布商业包。
- 推送到 `release/**` 时，由 `.github/workflows/commercial-release.yml` 生成 RC 候选版本，例如 `2.3.5-rc.123.abcdef0`，并推送固定版本商业镜像，但不默认同步公开交付仓库。
- 推送正式 tag `vX.Y.Z` 时，生成正式版本 `X.Y.Z`，并同步到 `Lynn-Lee/Sagitta-Deploy`。
- 手动触发商业 workflow 时，如果填写 `version`，生成指定正式版本；如果留空，生成快照版本；默认不发布到公开交付仓库，只有显式勾选发布时才同步公开发布仓库。
- 工作流会推送公开镜像到 `ghcr.io/lynn-lee/sagitta-control-backend:<version>` 和 `ghcr.io/lynn-lee/sagitta-control-frontend:<version>`。
- 工作流会更新 `Lynn-Lee/Sagitta-Deploy` 根目录，并把 zip、sha256、签名文件和 SBOM 放入 `releases/v<version>/`；同时创建或更新公开仓库的 `v<version>` GitHub Release。
- 为避免 GitHub Actions 制品存储配额被大包耗尽，商业部署包默认不上传为 Actions artifact；如确需临时留存，可配置仓库变量 `ENABLE_COMMERCIAL_RELEASE_ARTIFACT=true`。
- GitHub Actions 默认调度到本机 Ubuntu VM 的 self-hosted runner `sagitta-control-vm`，标签为 `[self-hosted, Linux, ARM64, sagitta-control]`；workflow 使用 `actions/checkout` 检出源码且不默认使用 GitHub 托管缓存，避免私有仓库 CI 被 hosted runner 或缓存计费状态阻断。
- 商业后端镜像在 GitHub Actions 中使用官方 PyPI 源并延长 pip 超时时间，避免 runner 访问依赖源时出现下载超时。

私有仓库需要配置 GitHub Secrets：

```text
MANIFEST_PRIVATE_KEY
PUBLIC_RELEASES_TOKEN
```

`MANIFEST_PRIVATE_KEY` 用于商业镜像 Manifest 签名。`PUBLIC_RELEASES_TOKEN` 必须是可写 `Lynn-Lee/Sagitta-Deploy` 的 GitHub token，建议只授予该公开仓库的 contents read/write 权限。

现有脚本入口：

```bash
VERSION=2.3.5 \
IMAGE_REPOSITORY=ghcr.io/<org>/sagitta-control \
MANIFEST_PRIVATE_KEY_FILE=/path/to/manifest_private_key \
./scripts/build-commercial-images.sh

python scripts/render-customer-package.py \
  --version 2.3.5 \
  --image-repository ghcr.io/<org>/sagitta-control \
  --output-dir dist-commercial \
  --package-name Sagitta-Control-v2.3.5
```

## 8. 验收清单

v2.1 交付验收需额外覆盖 Oracle 观测中心能力：

- Oracle 会话页可展示 RAC 实例号、OS PID、module/action、等待分类、阻塞实例和 PGA 字段；11g 环境下不应因缺失高版本字段导致会话采集失败。
- Oracle Top SQL / SQL 洞察优先展示 SQL Monitor 样本；当 SQL Monitor 或 AWR 权限不足时，应展示 warning 并降级到 `GV$SQL` 或当前会话 SQL。
- Oracle 慢 SQL 样本来源筛选包含 `oracle_sql_monitor`、`oracle_awr_sqlstat`、`oracle_cursor_cache`，执行计划分析可返回 DBMS_XPLAN 文本计划。
- Oracle 监控 SQL 仅执行只读动态性能视图查询，不包含 kill、dump、baseline、profile、patch 等变更类操作。

每个公开商业发布必须满足：

- 公开 Release 可下载 `Sagitta-Control-vX.Y.Z.zip` 和 `.sha256`。
- GHCR 镜像可匿名拉取。
- 部署包不需要源码即可启动。
- `docker-compose.yml` 和 Helm values 使用固定版本镜像。
- 首次部署自动进入 60 天全功能试用。
- 在线授权超过联网校验宽限期后会 fail closed。
- 试用到期后业务功能阻断，授权管理入口仍可访问。
- 在线激活、联网刷新和离线 challenge-response 均可用。
- License 项目码必须是 `sagitta-control`。
- `商业交付` → `交付与支持` 页能展示推广就绪度、试用/授权状态、客户 ID、正式激活部署指纹、客户环境用量和推广前待处理项；支持幂等初始化商业试用资源组、用户组、标准审批流和演示链路数据，且未接入实例时不得伪造活跃实例或保存真实数据库密码；验收报告包含 `可推广`、`需补配置` 或 `阻塞` 结论。
- 客户正式推广前必须执行客户包内 `prepare-go-live-env.sh` 和 `go-live-check.sh`。前者生成生产随机密钥和稳定部署 ID，后者严格校验生产环境变量、正式 License、客户 ID、部署指纹、活跃实例、实施向导、验收报告、运行健康和推广就绪度；任一失败均不得进入正式推广。
- 篡改商业镜像关键文件时完整性校验失败。
- 商业后端镜像不包含非白名单 Python 源码或字节码缓存。
- 商业前端镜像不包含 `.map` 文件或 `sourceMappingURL` 引用。
- 商业 Docker build context 不包含本地虚拟环境、依赖缓存、测试目录、历史发布包、私钥、License 文件或激活材料。
- Release 目录包含客户包签名、前后端镜像 SBOM 和 SBOM 校验/签名文件。
- 公开仓库和 Release 包不包含源码、私钥、token、真实 License、真实客户 ID、
  真实域名、部署指纹、内部验收记录、sourcemap、本地 `build:` 配置或 `latest`
  标签。

## 9. 推荐默认值

```text
Product Code: sagitta-control
Product Name: Sagitta Control
Edition: enterprise
Trial Days: 30
Release Tag: v2.3.5
Package Name: Sagitta-Control-v2.3.5.zip
Backend Image: ghcr.io/<org>/sagitta-control-backend:2.3.5
Frontend Image: ghcr.io/<org>/sagitta-control-frontend:2.3.5
License Server: License-Server-Center
Expired Behavior: 保留登录和授权管理入口，业务 API 阻断
```
