#!/usr/bin/env bash

set -Eeuo pipefail

TARGET_VERSION="${1:-2.0.0}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:8000/health}"
FRONTEND_HEALTH_URL="${FRONTEND_HEALTH_URL:-http://127.0.0.1/health}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-40}"
  local sleep_seconds="${4:-3}"

  log "Waiting for ${name}: ${url}"
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 5 "${url}" >/dev/null; then
      log "${name} is healthy"
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

[[ -f docker-compose.yml ]] || die "docker-compose.yml not found. Run this script from the customer package directory."
[[ -f .env ]] || die ".env not found. Copy .env.example to .env and configure it first."

mkdir -p "${BACKUP_DIR}"

log "Updating docker-compose.yml image tags to ${TARGET_VERSION}"
tmp_file="$(mktemp)"
sed -E "s#(ghcr.io/lynn-lee/sagittadb-(backend|frontend):)[0-9]+\.[0-9]+\.[0-9]+([-A-Za-z0-9.]+)?#\1${TARGET_VERSION}#g" docker-compose.yml > "${tmp_file}"
mv "${tmp_file}" docker-compose.yml

log "Pulling SagittaDB Enterprise images"
docker compose pull backend frontend celery_worker celery_beat

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_file="${BACKUP_DIR}/sagittadb_${timestamp}.sql.gz"
log "Creating PostgreSQL backup: ${backup_file}"
docker compose up -d postgres redis
docker compose exec -T postgres sh -ec \
  'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; pg_dump -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagittadb}" --no-owner --no-acl --format=plain' \
  | gzip > "${backup_file}"

log "Running database migrations"
docker compose run --rm backend alembic upgrade head

log "Recreating application services"
docker compose up -d

wait_for_url "backend" "${BACKEND_HEALTH_URL}" 40 3
wait_for_url "frontend" "${FRONTEND_HEALTH_URL}" 30 3

log "Upgrade finished. Backup: ${backup_file}"
docker compose ps
