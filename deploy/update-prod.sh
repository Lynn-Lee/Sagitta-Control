#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.yml"
ENV_FILE="${ROOT_DIR}/.env"
APP_SERVICES=(backend celery_worker celery_beat flower frontend)
BASE_SERVICES=(postgres redis)
DEFAULT_BACKEND_HEALTH_URL="http://127.0.0.1:8000/health"
DEFAULT_FRONTEND_HEALTH_URL="http://127.0.0.1/health"
DEFAULT_RELEASE_BRANCH="main"
DEFAULT_BACKUP_DIR="/data/sagittadb/backups"
DEFAULT_BACKUP_RETAIN_DAYS="7"

usage() {
  cat <<'EOF'
Usage:
  bash deploy/update-prod.sh [options]

Default flow:
  1. Check local tracked files are clean
  2. Fetch origin and fast-forward local main to origin/main, or checkout --ref
  3. Run pre-deploy PostgreSQL backup through the postgres container
  4. Build production images
  5. Ensure postgres/redis are running
  6. Run alembic migration
  7. Recreate application services
  8. Wait for health checks and show service status

Options:
  --ref <git-ref>          Deploy a specific tag/branch/commit. Defaults to origin/main.
  --skip-backup            Skip the pre-deploy database backup.
  --skip-migrate           Skip alembic upgrade head.
  --no-cache               Build Docker images with --no-cache.
  --prune                  Prune dangling Docker images after a successful deploy.
  --backend-health <url>   Backend health URL. Default: http://127.0.0.1:8000/health
  --frontend-health <url>  Frontend health URL. Default: http://127.0.0.1/health
  -h, --help               Show this help message.

Examples:
  bash deploy/update-prod.sh
  bash deploy/update-prod.sh --ref origin/main
  bash deploy/update-prod.sh --ref v1.0.1
  bash deploy/update-prod.sh --skip-backup --no-cache
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

ensure_clean_tracked_tree() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Tracked files have local changes. Commit, stash, or restore them before deploy."
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-30}"
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

show_recent_logs() {
  log "Recent logs for troubleshooting"
  compose logs --tail=120 backend frontend celery_worker || true
}

checkout_default_ref() {
  log "Checking out ${DEFAULT_RELEASE_BRANCH} and fast-forwarding to origin/${DEFAULT_RELEASE_BRANCH}"
  if git show-ref --verify --quiet "refs/heads/${DEFAULT_RELEASE_BRANCH}"; then
    git checkout "${DEFAULT_RELEASE_BRANCH}"
    git merge --ff-only "origin/${DEFAULT_RELEASE_BRANCH}"
  else
    git checkout -b "${DEFAULT_RELEASE_BRANCH}" "origin/${DEFAULT_RELEASE_BRANCH}"
  fi
}

run_container_backup() {
  local backup_dir="${BACKUP_DIR:-${DEFAULT_BACKUP_DIR}}"
  local retain_days="${BACKUP_RETAIN_DAYS:-${DEFAULT_BACKUP_RETAIN_DAYS}}"
  local postgres_db
  local timestamp filename filepath

  postgres_db="$(compose exec -T postgres sh -ec 'printf "%s" "${POSTGRES_DB:-sagittadb}"')"
  timestamp="$(date +%Y%m%d_%H%M%S)"
  filename="sagittadb_${postgres_db}_${timestamp}.sql.gz"
  filepath="${backup_dir}/${filename}"

  mkdir -p "${backup_dir}"

  log "Running container PostgreSQL backup: ${filepath}"
  compose exec -T postgres sh -ec \
    'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; pg_dump -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagittadb}" --no-owner --no-acl --format=plain' \
    | gzip > "${filepath}"

  log "Backup completed: ${filepath} ($(du -sh "${filepath}" | cut -f1))"

  log "Removing backups older than ${retain_days} days from ${backup_dir}"
  find "${backup_dir}" -name "sagittadb_*.sql.gz" -mtime "+${retain_days}" -delete
}

REF=""
SKIP_BACKUP=0
SKIP_MIGRATE=0
NO_CACHE=0
PRUNE=0
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-${DEFAULT_BACKEND_HEALTH_URL}}"
FRONTEND_HEALTH_URL="${FRONTEND_HEALTH_URL:-${DEFAULT_FRONTEND_HEALTH_URL}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 2 ]] || die "--ref requires a value"
      REF="$2"
      shift 2
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    --skip-migrate)
      SKIP_MIGRATE=1
      shift
      ;;
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    --prune)
      PRUNE=1
      shift
      ;;
    --backend-health)
      [[ $# -ge 2 ]] || die "--backend-health requires a value"
      BACKEND_HEALTH_URL="$2"
      shift 2
      ;;
    --frontend-health)
      [[ $# -ge 2 ]] || die "--frontend-health requires a value"
      FRONTEND_HEALTH_URL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

trap 'log "Deployment failed at line ${LINENO}"; show_recent_logs' ERR

require_cmd git
require_cmd docker
require_cmd curl

cd "${ROOT_DIR}"

[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
[[ -f "${ENV_FILE}" ]] || die ".env not found: ${ENV_FILE}. Create it from .env.example before deploy."

ensure_clean_tracked_tree

old_revision="$(git rev-parse --short HEAD)"
log "Current revision: ${old_revision}"

log "Fetching latest Git refs"
git fetch --tags origin

if [[ -n "${REF}" ]]; then
  log "Checking out target ref: ${REF}"
  git checkout "${REF}"
else
  checkout_default_ref
fi

new_revision="$(git rev-parse --short HEAD)"
log "Target revision: ${new_revision}"

if [[ ${SKIP_BACKUP} -eq 0 ]]; then
  log "Ensuring base services are running before backup: ${BASE_SERVICES[*]}"
  compose up -d "${BASE_SERVICES[@]}"
  run_container_backup
else
  log "Skipping database backup as requested"
fi

build_args=()
if [[ ${NO_CACHE} -eq 1 ]]; then
  build_args+=(--no-cache)
fi

log "Building production images: ${APP_SERVICES[*]}"
compose build "${build_args[@]}" "${APP_SERVICES[@]}"

log "Ensuring base services are running: ${BASE_SERVICES[*]}"
compose up -d "${BASE_SERVICES[@]}"

if [[ ${SKIP_MIGRATE} -eq 0 ]]; then
  log "Running database migrations"
  compose run --rm backend alembic upgrade head
else
  log "Skipping database migrations as requested"
fi

log "Recreating updated application services: ${APP_SERVICES[*]}"
compose up -d --no-deps "${APP_SERVICES[@]}"

wait_for_url "backend" "${BACKEND_HEALTH_URL}" 40 3
wait_for_url "frontend" "${FRONTEND_HEALTH_URL}" 30 3

log "Current service status"
compose ps

if [[ ${PRUNE} -eq 1 ]]; then
  log "Pruning dangling Docker images"
  docker image prune -f
fi

log "Deployment finished: ${old_revision} -> ${new_revision}"
