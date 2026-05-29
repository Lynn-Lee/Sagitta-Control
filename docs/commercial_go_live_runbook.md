# SagittaDB Enterprise 生产部署实战手册

本文记录 AAAAA 客户在 ECS 上完成 SagittaDB Enterprise v2.2.0 正式部署时遇到的问题和处理结论，用作后续客户 go-live 的标准排障清单。

## 1. 部署前信息

正式部署前至少确认以下信息：

- 客户 ID，例如 `AAAAA`。
- 端口方案，例如由正式环境接管 `80/8000`，如使用 HTTPS 还需要 `443`。
- 访问域名和 DNS 管理方，例如 `sagitta.loveai.asia` / Cloudflare。
- 管理员初始密码策略，必须在初始化后替换默认密码。
- 首个测试或生产同构数据库实例，确保 go-live 前至少有一个活跃实例。
- 是否停掉旧的 source-test 或演示环境，以及旧环境的数据保留方式。
- 正式 License 激活码，或离线 challenge-response 流程负责人。
- 通知渠道配置，邮件、飞书、钉钉或企微至少一种。

## 2. 镜像架构校验

客户服务器通常是 `linux/amd64`。如果商业镜像从 Apple Silicon 或其他 arm64 构建机发布，可能只包含 `linux/arm64` manifest，客户机上会出现：

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

`scripts/build-commercial-images.sh` 默认以 `DOCKER_PLATFORM=linux/amd64` 构建。确需发布多架构镜像时，应使用 buildx 显式发布 manifest list，并分别验证 `linux/amd64` 和 `linux/arm64`。

如果必须在客户 ECS 上临时补构 amd64 镜像：

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

## 5. Cloudflare 与 HTTPS

Cloudflare 排障时先区分三个层面：

```bash
# 源站本机
curl -sk https://127.0.0.1/health

# 直连源站公网 IP，带 Host
curl --noproxy '*' -sk https://<origin-ip>/health -H 'Host: <domain>'

# 正常域名
curl -i https://<domain>/health
```

结论判断：

- 直连源站正常，但橙云代理返回 `525`：问题在 Cloudflare 到源站的 TLS 握手策略，不是 SagittaDB 应用。
- `HEAD /health` 返回 `405`：后端只允许 GET，不代表健康检查失败。
- DNS 改成“仅 DNS”后，权威 DNS 已返回源站 IP，但本地仍看到 Cloudflare IP：等待本地 DNS 缓存过期，或重启浏览器/切换网络验证。
- `198.18.*` 解析结果通常来自本机代理或虚拟网络，不可作为公网权威 DNS 结论。

如果使用 Cloudflare 橙云代理：

- SSL/TLS 模式建议至少 `Full`，生产环境优先 `Full strict`。
- `Full strict` 需要源站证书被 Cloudflare 接受，可使用 Cloudflare Origin Certificate 或公开 CA 证书。
- 源站 443 建议由宿主机 nginx/caddy 或稳定边缘代理直接监听，再反代到容器前端。

如果短时间内出现 525 且源站直连已经正常，最快恢复路径是把 DNS 记录从橙云 `Proxied` 改成灰云 `DNS only`。源站必须已经安装覆盖该域名的有效证书。

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

创建 SagittaDB 实例后必须调用连接测试，确认 `success=true`。

## 7. 敏感信息清理

客户现场临时操作后检查：

- 删除 `/tmp` 下激活 payload、临时登录响应、私钥和临时 Dockerfile。
- 删除临时构建源码目录。
- 不把 `.env`、License、私钥、激活码、数据库密码提交到 Git。
- `docker compose down` 只用于停旧环境容器，确认不会删除需要保留的 volume。
- 保留客户包 zip、sha256、签名和 go-live check 输出，作为交付记录。
