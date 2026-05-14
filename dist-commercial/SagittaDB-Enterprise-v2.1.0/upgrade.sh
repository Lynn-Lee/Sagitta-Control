#!/usr/bin/env bash

set -Eeuo pipefail

TARGET_VERSION="${1:-2.1.0}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:8000/health}"
FRONTEND_HEALTH_URL="${FRONTEND_HEALTH_URL:-http://127.0.0.1/health}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "错误：$*"
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-40}"
  local sleep_seconds="${4:-3}"

  log "等待 ${name} 健康检查：${url}"
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 5 "${url}" >/dev/null; then
      log "${name} 已健康"
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  return 1
}

[[ -f docker-compose.yml ]] || die "未找到 docker-compose.yml，请在客户部署包目录中运行本脚本。"
[[ -f .env ]] || die "未找到 .env，请先复制 .env.example 为 .env 并完成配置。"

mkdir -p "${BACKUP_DIR}"

log "更新 docker-compose.yml 镜像标签为 ${TARGET_VERSION}"
tmp_file="$(mktemp)"
sed -E "s#(ghcr.io/lynn-lee/sagittadb-(backend|frontend):)[0-9]+\.[0-9]+\.[0-9]+([-A-Za-z0-9.]+)?#\1${TARGET_VERSION}#g" docker-compose.yml > "${tmp_file}"
mv "${tmp_file}" docker-compose.yml

log "拉取 SagittaDB Enterprise 镜像"
docker compose pull backend frontend celery_worker celery_beat

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_file="${BACKUP_DIR}/sagittadb_${timestamp}.sql.gz"
log "创建 PostgreSQL 备份：${backup_file}"
docker compose up -d postgres redis
docker compose exec -T postgres sh -ec \
  'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; pg_dump -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagittadb}" --no-owner --no-acl --format=plain' \
  | gzip > "${backup_file}"

log "执行数据库迁移"
docker compose run --rm backend alembic upgrade head

log "重建应用服务"
docker compose up -d

wait_for_url "backend" "${BACKEND_HEALTH_URL}" 40 3
wait_for_url "frontend" "${FRONTEND_HEALTH_URL}" 30 3

log "升级完成。备份文件：${backup_file}"
docker compose ps
