# SagittaDB Enterprise vX.Y.Z

## Images

- `ghcr.io/<org>/sagittadb-backend:X.Y.Z`
- `ghcr.io/<org>/sagittadb-frontend:X.Y.Z`

## Install

Download `SagittaDB-Enterprise-vX.Y.Z.zip`, verify the checksum, unzip it, then follow the included `README.md`.

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

## Trial And License

First deployment starts a 30-day full-feature trial. After the trial expires, business APIs are blocked and the license management page remains available.

For commercial authorization, contact SagittaDB support and provide the deployment fingerprint shown in the license management page.

## Security Notes

This package contains deployment files only. It does not include SagittaDB source code, private keys, customer licenses, activation codes, or registry credentials.
