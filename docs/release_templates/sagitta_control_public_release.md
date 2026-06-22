# Sagitta Control vX.Y.Z

## 镜像

- `ghcr.io/<org>/sagitta-control-backend:X.Y.Z`
- `ghcr.io/<org>/sagitta-control-frontend:X.Y.Z`

## 安装

下载 `Sagitta-Control-vX.Y.Z.zip` 和 sha256 文件，校验后解压，并按包内 `README.md` 和 `docs/installation.md` 部署。

```bash
wget https://github.com/Lynn-Lee/Sagitta-Control/releases/download/vX.Y.Z/Sagitta-Control-vX.Y.Z.zip
wget https://github.com/Lynn-Lee/Sagitta-Control/releases/download/vX.Y.Z/Sagitta-Control-vX.Y.Z.zip.sha256
sha256sum -c Sagitta-Control-vX.Y.Z.zip.sha256
unzip Sagitta-Control-vX.Y.Z.zip
cd Sagitta-Control-vX.Y.Z
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

启动后先检查：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
```

## 试用与授权

首次部署自动进入 60 天全功能试用期。试用到期后，业务 API 会被阻断，授权管理页仍可访问。

在线授权默认需要至少每 7 天成功联网刷新一次；长期离线部署请使用 challenge-response 离线授权。

获取商业授权时，请联系 Sagitta Control 支持团队。在授权管理页输入客户 ID 后复制“正式激活部署指纹”，并将该指纹提供给授权运营侧生成激活码。HTTP 试用部署会自动使用兼容复制方式，若浏览器仍阻止复制，可直接手动选择页面展示的完整指纹。

## 安全说明

本部署包只包含部署文件，不包含 Sagitta Control 源码、私钥、客户 License、激活码或镜像仓库凭据。
Release 同时提供客户包签名文件、前后端镜像 CycloneDX SBOM 及其校验/签名材料。
