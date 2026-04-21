#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.yml"
BACKUP_SCRIPT="${ROOT_DIR}/deploy/backup/backup-postgres.sh"
SERVICES=(backend celery_worker celery_beat flower frontend)

usage() {
  cat <<'EOF'
Usage:
  bash deploy/update-prod.sh [--ref <git-ref>] [--skip-backup]

Options:
  --ref <git-ref>  Update to the specified tag/branch/commit. Defaults to current branch.
  --skip-backup    Skip the pre-deploy database backup.
  -h, --help       Show this help message.
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

ensure_clean_tracked_tree() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Tracked files have local changes. Commit, stash, or restore them before publishing."
  fi
}

REF=""
SKIP_BACKUP=0

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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

require_cmd git
require_cmd docker

cd "${ROOT_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  die "Compose file not found: ${COMPOSE_FILE}"
fi

ensure_clean_tracked_tree

if [[ ${SKIP_BACKUP} -eq 0 ]]; then
  [[ -x "${BACKUP_SCRIPT}" ]] || die "Backup script is not executable: ${BACKUP_SCRIPT}"
  log "Running pre-deploy database backup"
  bash "${BACKUP_SCRIPT}"
else
  log "Skipping database backup as requested"
fi

log "Fetching latest Git refs"
git fetch --tags origin

if [[ -n "${REF}" ]]; then
  log "Checking out target ref: ${REF}"
  git checkout "${REF}"
else
  current_branch="$(git branch --show-current)"
  [[ -n "${current_branch}" ]] || die "Detached HEAD detected. Re-run with --ref <tag-or-commit>."
  log "Fast-forwarding current branch: ${current_branch}"
  git pull --ff-only origin "${current_branch}"
fi

log "Building production images"
docker compose -f "${COMPOSE_FILE}" build "${SERVICES[@]}"

log "Running database migrations"
docker compose -f "${COMPOSE_FILE}" run --rm backend alembic upgrade head

log "Restarting updated services"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${SERVICES[@]}"

log "Current service status"
docker compose -f "${COMPOSE_FILE}" ps

log "Deployment finished"
