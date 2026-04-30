# SagittaDB Enterprise v__SAGITTADB_VERSION__

This package is the customer deployment artifact for SagittaDB Enterprise. It contains deployment configuration only. Application code is delivered through versioned Docker images.

## Images

- Backend: `__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- Frontend: `__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`

Do not use `latest` for production deployments. Keep the explicit version tag in `docker-compose.yml`.

## First Deployment

```bash
cp .env.example .env
# Edit .env and replace every CHANGE_ME value.
docker login ghcr.io
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

Open `http://<server>/` after the frontend service is healthy.

## Upgrade

For an online upgrade:

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

For a manual upgrade, update image tags in `docker-compose.yml`, then run:

```bash
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
curl -fsS http://127.0.0.1:8000/health
```

## Offline Image Import

If the server cannot access the registry, import images provided by SagittaDB support:

```bash
docker load < sagittadb-backend-__SAGITTADB_VERSION__.tar
docker load < sagittadb-frontend-__SAGITTADB_VERSION__.tar
docker compose up -d
```

## License

Import the license file from the SagittaDB system administration page after login. Keep license files outside this deployment package when sharing logs or configuration.
