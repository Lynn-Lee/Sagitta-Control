# Sagitta Control Enterprise 生产部署排障模板

本文用于记录 Sagitta Control Enterprise 客户现场 go-live 的通用排障步骤和案例复盘模板。
公开仓库只保留可复用方法，不记录真实客户名称、客户 ID、域名、公网 IP、
License、token、内部验收结论或授权中心操作记录。

## 1. 部署前信息

正式部署前至少确认以下信息，并在客户交付记录中使用受控渠道保存真实值：

- 客户标识：文档中统一写作 `<customer_id>`，不得写入真实客户 ID。
- 访问入口：文档中统一写作 `<domain>`、`<origin-ip>`，不得写入真实域名、公网 IP 或 DNS 账号信息。
- 端口方案：前端、后端 API、HTTPS、反向代理和内网管理端口。
- 管理员初始密码策略：初始化后必须替换默认密码，并确认 2FA 策略。
- 首个测试或生产同构数据库实例：go-live 前至少接入一个活跃实例。
- 旧环境处理方式：是否停用旧 source-test、演示环境或临时 compose project，以及数据保留方案。
- License 授权方式：在线激活或离线 challenge-response，真实激活码和 response 文件不得进入仓库。
- 通知渠道：邮件、飞书、钉钉或企微至少一种，并完成连通性测试。

## 2. 镜像架构校验

客户服务器通常是 `linux/amd64`。如果商业镜像从 Apple Silicon 或其他
arm64 构建机发布，可能只包含 `linux/arm64` manifest，客户机上会出现：

```text
no matching manifest for linux/amd64 in the manifest list entries
```

发布前必须检查镜像 manifest：

```bash
VERSION=2.2.0 \
IMAGE_REPOSITORY=ghcr.io/<org>/sagittadb \
EXPECTED_PLATFORMS=linux/amd64 \
./scripts/validate-commercial-images.sh
```

`scripts/build-commercial-images.sh` 默认以 `DOCKER_PLATFORM=linux/amd64` 构建。
确需发布多架构镜像时，应使用 buildx 显式发布 manifest list，并分别验证
`linux/amd64` 和 `linux/arm64`。

如果必须在客户现场临时补构 amd64 镜像：

- 使用 BuildKit secret 挂载 Manifest 私钥，不要把私钥复制进镜像层。
- 构建目录排除 `.git`、`frontend/node_modules`、`backend/.venv`、`dist-commercial`、缓存和历史包。
- 构建完成后删除临时源码、私钥、临时 Dockerfile 和登录材料，并执行 `docker builder prune -f` 回收空间。

## 3. License 激活

客户包内 `verify-license.sh` 使用带尾斜杠的登录接口：

```text
POST /api/v1/auth/login/
```

不要使用无尾斜杠的 `/auth/login`，否则某些 `curl` 调用会收到 307 redirect，脚本管道解析 JSON 时失败。

正式激活需要授权中心已录入以下材料：

```text
project=sagittadb
product=sagittadb
customer_id=<customer_id>
deployment_fingerprint=<fingerprint>
```

激活后必须确认：

- `license.status=licensed`
- `license.is_trial=false`
- `license.activation_customer_id` 与 `.env` 中 `LICENSE_CUSTOMER_ID` 一致
- `license.activation_deployment_fingerprint` 非空

真实客户 ID、正式激活部署指纹、激活码、离线 Challenge/Response、授权中心状态
流转记录只保存在受控交付系统或授权中心，不写入公开仓库、公开 Release、
PR 描述、提交信息或支持群截图。

## 4. Go-live 门禁

正式推广前必须执行：

```bash
./prepare-go-live-env.sh --customer-id <customer_id>

docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d

./go-live-check.sh \
  --api-base-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1/ \
  --username admin \
  --password '<admin-password>'
```

`go-live-check.sh` 的失败项不要用假配置绕过。常见剩余项：

- `License 为正式授权`：需要在线激活码或离线 response。
- `通知链路`：至少配置邮件、飞书、钉钉或企微中的一种，并执行连通性测试。
- `实施交付向导已完成`：如果客户选择本地账号认证，应在交付记录中明确“本地账号认证方案已确认”；如果使用 LDAP/CAS/OIDC/企业应用登录，则完成对应配置后再勾选。

验收报告可以在产品内生成 Markdown/JSON，但公开仓库只保留模板化结论和检查项，
不保留真实客户验收截图、实例名称、审批人、账号、数据量或授权流水。

## 5. DNS 与 HTTPS

DNS、CDN 或反向代理排障时先区分三个层面：

```bash
# 源站本机
curl -sk https://127.0.0.1/health

# 直连源站公网 IP，带 Host
curl --noproxy '*' -sk https://<origin-ip>/health -H 'Host: <domain>'

# 正常域名
curl -i https://<domain>/health
```

结论判断：

- 直连源站正常，但 CDN 代理返回 TLS 握手错误：问题通常在 CDN 到源站的证书信任、
  TLS 模式或 SNI 配置，不是 Sagitta Control 应用。
- `HEAD /health` 返回 `405`：后端只允许 GET，不代表健康检查失败。
- DNS 改成直连后，权威 DNS 已返回源站 IP，但本地仍看到旧 IP：等待本地 DNS 缓存过期，或重启浏览器/切换网络验证。
- `198.18.*` 解析结果通常来自本机代理或虚拟网络，不可作为公网权威 DNS 结论。

如果使用 CDN 代理：

- SSL/TLS 模式建议至少启用端到端加密，生产环境优先使用严格证书校验。
- 严格证书校验需要源站证书被 CDN 接受，可使用 CDN Origin Certificate 或公开 CA 证书。
- 源站 443 建议由宿主机 nginx/caddy 或稳定边缘代理直接监听，再反代到容器前端。

如果短时间内出现 TLS 代理错误且源站直连已经正常，可以临时切换为 DNS only
或直连模式验证。源站必须已经安装覆盖 `<domain>` 的有效证书。

## 6. 首个数据库实例

正式客户环境至少接入一个活跃实例。演示或验收时可以在同一 Docker network 内启动一个不暴露公网端口的 PostgreSQL 样例实例：

```bash
docker run -d --name <customer>-sample-pg \
  --network <compose-project>_default \
  --restart always \
  -e POSTGRES_DB=<db> \
  -e POSTGRES_USER=<user> \
  -e POSTGRES_PASSWORD='<password>' \
  -v <customer>_sample_pg_data:/var/lib/postgresql/data \
  postgres:16-alpine
```

创建 Sagitta Control 实例后必须调用连接测试，确认 `success=true`。样例实例只用于
验证流程，真实客户数据库连接串、账号、库名、表名和脱敏前数据不得写入公开文档。

## 7. 敏感信息清理

客户现场临时操作后检查：

- 删除 `/tmp` 下激活 payload、临时登录响应、私钥和临时 Dockerfile。
- 删除临时构建源码目录。
- 不把 `.env`、License、私钥、激活码、数据库密码、客户 ID、部署指纹、真实域名、
  公网 IP、token 或内部验收记录提交到 Git。
- `docker compose down` 只用于停旧环境容器，确认不会删除需要保留的 volume。
- 客户包 zip、sha256、签名、go-live check 输出和授权状态流转记录只在受控交付
  系统留存；公开材料仅引用模板化检查项。

## 8. 案例复盘模板

每次客户现场问题复盘建议按以下模板记录，并在进入公开仓库前完成脱敏：

```text
问题类型：<镜像架构|License|DNS/HTTPS|实例接入|通知|验收门禁|其他>
影响范围：<部署阻塞|功能降级|体验问题|已规避>
环境摘要：<版本、部署方式、CPU 架构、网络形态，禁止写真实客户标识>
现象：<错误摘要或脱敏日志片段>
定位步骤：<关键命令和判断>
处理结论：<可复用方案>
后续动作：<文档、脚本、产品或流程改进>
公开边界：<确认无真实客户 ID、域名、License、token、内部验收记录>
```
