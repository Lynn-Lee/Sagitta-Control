# SagittaDB Enterprise vX.Y.Z

## 镜像

- `ghcr.io/<org>/sagittadb-backend:X.Y.Z`
- `ghcr.io/<org>/sagittadb-frontend:X.Y.Z`

## 安装

下载 `SagittaDB-Enterprise-vX.Y.Z.zip`，校验 sha256 后解压，并按包内 `README.md` 部署。

```bash
sha256sum -c SagittaDB-Enterprise-vX.Y.Z.zip.sha256
unzip SagittaDB-Enterprise-vX.Y.Z.zip
cd SagittaDB-Enterprise-vX.Y.Z
cp .env.example .env
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

## 试用与授权

首次部署自动进入 30 天全功能试用期。试用到期后，业务 API 会被阻断，授权管理页仍可访问。

在线授权默认需要至少每 7 天成功联网刷新一次；长期离线部署请使用 challenge-response 离线授权。

获取商业授权时，请联系 SagittaDB 支持团队，并提供授权管理页展示的部署指纹。

## 安全说明

本部署包只包含部署文件，不包含 SagittaDB 源码、私钥、客户 License、激活码或镜像仓库凭据。
Release 同时提供客户包签名文件、前后端镜像 CycloneDX SBOM 及其校验/签名材料。
