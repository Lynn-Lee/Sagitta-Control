#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.yml"
ENV_FILE="${ROOT_DIR}/.env"
APP_SERVICES=(backend celery_worker celery_beat flower frontend)
BACKEND_SERVICES=(backend celery_worker celery_beat flower)
FRONTEND_SERVICES=(frontend)
BASE_SERVICES=(postgres redis)
DEFAULT_BACKEND_HEALTH_URL="http://127.0.0.1:8000/health"
DEFAULT_FRONTEND_HEALTH_URL="http://127.0.0.1/health"
DEFAULT_GIT_REMOTE="origin"
DEFAULT_RELEASE_BRANCH="main"
DEFAULT_BACKUP_DIR="/data/sagittadb/backups"
DEFAULT_BACKUP_RETAIN_DAYS="7"
DB_CHANGE_PATTERNS=(
  "backend/alembic/"
  "backend/app/models/"
  "backend/app/core/database.py"
  "docker-compose.yml"
  "deploy/docker-compose.yml"
  "deploy/helm/"
)
BACKEND_CHANGE_PATTERNS=(
  "backend/"
)
FRONTEND_CHANGE_PATTERNS=(
  "frontend/"
  "deploy/nginx.conf"
)
FULL_DEPLOY_CHANGE_PATTERNS=(
  "docker-compose.yml"
  "deploy/docker-compose.yml"
  "deploy/update-prod.sh"
)

usage() {
  cat <<'EOF'
用法：
  bash deploy/update-prod.sh [options]

默认流程：
  1. 检查本地已跟踪文件是否干净
  2. 通过 SSH Git remote 拉取 origin，并把本地 main 快进到 origin/main，或切换到 --ref 指定版本
  3. 检测目标版本是否包含数据库相关变更；如包含则通过 postgres 容器执行部署前 PostgreSQL 备份
  4. 根据变更范围选择构建后端共享镜像、前端镜像或跳过镜像构建
  5. 确保 postgres/redis 正在运行
  6. 仅在数据库相关变更时执行 alembic 迁移
  7. 按变更范围重建应用服务
  8. 等待健康检查并展示服务状态

默认约定：
  - ECS 测试/生产源码部署目录直接保留 Git 工作区，例如 /opt/sagittadb/source。
  - origin 使用 SSH deploy key，例如 git@github.com-sagittadb:Lynn-Lee/SagittaDB.git。
  - 未显式传 --ref 时，脚本部署 origin/main 的最新快进版本。

选项：
  --ref <git-ref>          部署指定 tag、branch 或 commit，默认 origin/main。
  --force-backup           即使未检测到数据库相关变更，也执行部署前数据库备份。
  --skip-backup            跳过部署前数据库备份；优先级高于 --force-backup。
  --skip-migrate           跳过 alembic upgrade head。
  --full                   强制构建并重建全部应用服务。
  --no-cache               使用 --no-cache 构建 Docker 镜像。
  --prune                  部署成功后清理悬空 Docker 镜像。
  --backend-health <url>   后端健康检查 URL，默认 http://127.0.0.1:8000/health
  --frontend-health <url>  前端健康检查 URL，默认 http://127.0.0.1/health
  -h, --help               显示帮助信息。

环境变量：
  GIT_REMOTE               Git remote 名称，默认 origin。
  RELEASE_BRANCH           默认发布分支，默认 main。
  REQUIRE_SSH_GIT_REMOTE   是否要求 remote 为 SSH URL，默认 1；临时 HTTPS 凭据场景可设为 0。
  BACKUP_DIR               数据库备份目录，默认 /data/sagittadb/backups。
  BACKUP_RETAIN_DAYS       备份保留天数，默认 7。
  COMPOSE_PROJECT_NAME     Compose 项目名；ECS 测试环境使用 sagittadb-source-test。
  SAGITTADB_BACKEND_IMAGE  后端/Worker/Beat/Flower 共享镜像名，默认 <COMPOSE_PROJECT_NAME>-backend:latest。
  SAGITTADB_FRONTEND_IMAGE 前端镜像名，默认 <COMPOSE_PROJECT_NAME>-frontend:latest。

示例：
  COMPOSE_PROJECT_NAME=sagittadb-source-test bash deploy/update-prod.sh
  bash deploy/update-prod.sh
  bash deploy/update-prod.sh --ref origin/main
  bash deploy/update-prod.sh --ref v2.0.0
  bash deploy/update-prod.sh --force-backup
  bash deploy/update-prod.sh --full
  bash deploy/update-prod.sh --skip-backup --no-cache
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "错误：$*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少必需命令：$1"
}

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

ensure_clean_tracked_tree() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "已跟踪文件存在本地改动，请先提交、暂存或恢复后再部署。"
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-30}"
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

show_recent_logs() {
  log "输出最近日志用于排障"
  compose logs --tail=120 backend frontend celery_worker || true
}

ensure_git_remote_ready() {
  local remote_url

  if ! remote_url="$(git remote get-url "${GIT_REMOTE_NAME}" 2>/dev/null)"; then
    die "未找到 Git remote：${GIT_REMOTE_NAME}。请先配置 origin SSH remote，例如 git@github.com-sagittadb:Lynn-Lee/SagittaDB.git。"
  fi

  log "Git remote ${GIT_REMOTE_NAME}: ${remote_url}"

  if [[ "${REQUIRE_SSH_GIT_REMOTE}" == "1" && ! "${remote_url}" =~ ^(git@|ssh://) ]]; then
    die "生产发布要求使用 SSH Git remote。当前 ${GIT_REMOTE_NAME}=${remote_url}。请配置 GitHub deploy key 后执行：git remote set-url ${GIT_REMOTE_NAME} git@github.com-sagittadb:Lynn-Lee/SagittaDB.git；如确需使用 HTTPS，可临时设置 REQUIRE_SSH_GIT_REMOTE=0。"
  fi

  log "校验 Git 远端访问"
  git ls-remote --exit-code "${GIT_REMOTE_NAME}" HEAD >/dev/null
}

checkout_default_ref() {
  log "切换到 ${RELEASE_BRANCH_NAME} 并快进到 ${GIT_REMOTE_NAME}/${RELEASE_BRANCH_NAME}"
  if git show-ref --verify --quiet "refs/heads/${RELEASE_BRANCH_NAME}"; then
    git checkout "${RELEASE_BRANCH_NAME}"
    git merge --ff-only "${GIT_REMOTE_NAME}/${RELEASE_BRANCH_NAME}"
  else
    git checkout -b "${RELEASE_BRANCH_NAME}" "${GIT_REMOTE_NAME}/${RELEASE_BRANCH_NAME}"
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

  log "通过容器执行 PostgreSQL 备份：${filepath}"
  compose exec -T postgres sh -ec \
    'export PGPASSWORD="${POSTGRES_PASSWORD:-}"; pg_dump -U "${POSTGRES_USER:-sagitta}" -d "${POSTGRES_DB:-sagittadb}" --no-owner --no-acl --format=plain' \
    | gzip > "${filepath}"

  log "备份完成：${filepath} ($(du -sh "${filepath}" | cut -f1))"

  log "从 ${backup_dir} 清理超过 ${retain_days} 天的备份"
  find "${backup_dir}" -name "sagittadb_*.sql.gz" -mtime "+${retain_days}" -delete
}

db_changes_between_revisions() {
  local old_ref="$1"
  local new_ref="$2"
  local changed_file pattern

  if [[ "${old_ref}" == "${new_ref}" ]]; then
    return 1
  fi

  while IFS= read -r changed_file; do
    [[ -n "${changed_file}" ]] || continue
    for pattern in "${DB_CHANGE_PATTERNS[@]}"; do
      if [[ "${changed_file}" == "${pattern}"* ]]; then
        printf '%s\n' "${changed_file}"
        return 0
      fi
    done
  done < <(git diff --name-only "${old_ref}" "${new_ref}")

  return 1
}

path_matches_patterns() {
  local changed_file="$1"
  shift
  local pattern
  for pattern in "$@"; do
    if [[ "${changed_file}" == "${pattern}"* ]]; then
      return 0
    fi
  done
  return 1
}

changed_files_match() {
  local changed_files="$1"
  shift
  local changed_file

  [[ -n "${changed_files}" ]] || return 1
  while IFS= read -r changed_file; do
    [[ -n "${changed_file}" ]] || continue
    if path_matches_patterns "${changed_file}" "$@"; then
      printf '%s\n' "${changed_file}"
      return 0
    fi
  done <<< "${changed_files}"
  return 1
}

join_by_space() {
  local IFS=" "
  printf '%s' "$*"
}

REF=""
SKIP_BACKUP=0
FORCE_BACKUP=0
SKIP_MIGRATE=0
FORCE_FULL_DEPLOY="${FORCE_FULL_DEPLOY:-0}"
NO_CACHE=0
PRUNE=0
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-${DEFAULT_BACKEND_HEALTH_URL}}"
FRONTEND_HEALTH_URL="${FRONTEND_HEALTH_URL:-${DEFAULT_FRONTEND_HEALTH_URL}}"
GIT_REMOTE_NAME="${GIT_REMOTE:-${DEFAULT_GIT_REMOTE}}"
RELEASE_BRANCH_NAME="${RELEASE_BRANCH:-${DEFAULT_RELEASE_BRANCH}}"
REQUIRE_SSH_GIT_REMOTE="${REQUIRE_SSH_GIT_REMOTE:-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      [[ $# -ge 2 ]] || die "--ref 需要提供值"
      REF="$2"
      shift 2
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    --force-backup)
      FORCE_BACKUP=1
      shift
      ;;
    --skip-migrate)
      SKIP_MIGRATE=1
      shift
      ;;
    --full)
      FORCE_FULL_DEPLOY=1
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
      [[ $# -ge 2 ]] || die "--backend-health 需要提供值"
      BACKEND_HEALTH_URL="$2"
      shift 2
      ;;
    --frontend-health)
      [[ $# -ge 2 ]] || die "--frontend-health 需要提供值"
      FRONTEND_HEALTH_URL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数：$1"
      ;;
  esac
done

trap 'log "部署在第 ${LINENO} 行失败"; show_recent_logs' ERR

require_cmd git
require_cmd docker
require_cmd curl

cd "${ROOT_DIR}"

compose_project_name="${COMPOSE_PROJECT_NAME:-sagittadb}"
export SAGITTADB_BACKEND_IMAGE="${SAGITTADB_BACKEND_IMAGE:-${compose_project_name}-backend:latest}"
export SAGITTADB_FRONTEND_IMAGE="${SAGITTADB_FRONTEND_IMAGE:-${compose_project_name}-frontend:latest}"

[[ -f "${COMPOSE_FILE}" ]] || die "未找到 Compose 文件：${COMPOSE_FILE}"
[[ -f "${ENV_FILE}" ]] || die "未找到 .env：${ENV_FILE}，请在部署前从 .env.example 创建。"

ensure_clean_tracked_tree

old_revision="$(git rev-parse --short HEAD)"
old_revision_full="$(git rev-parse HEAD)"
log "当前版本：${old_revision}"

ensure_git_remote_ready

log "拉取最新 Git 引用"
git fetch --tags "${GIT_REMOTE_NAME}"

if [[ -n "${REF}" ]]; then
  log "切换到目标 ref：${REF}"
  git checkout "${REF}"
else
  checkout_default_ref
fi

new_revision="$(git rev-parse --short HEAD)"
new_revision_full="$(git rev-parse HEAD)"
log "目标版本：${new_revision}"

changed_files="$(git diff --name-only "${old_revision_full}" "${new_revision_full}")"
if [[ -n "${changed_files}" ]]; then
  log "本次变更文件："
  while IFS= read -r changed_file; do
    [[ -n "${changed_file}" ]] && log "  - ${changed_file}"
  done <<< "${changed_files}"
else
  log "当前版本与目标版本一致，未检测到代码变更"
fi

full_deploy_reason=""
backend_change_reason=""
frontend_change_reason=""
if [[ "${FORCE_FULL_DEPLOY}" == "1" ]]; then
  full_deploy_reason="按 --full 要求强制全量应用更新"
elif full_deploy_reason="$(changed_files_match "${changed_files}" "${FULL_DEPLOY_CHANGE_PATTERNS[@]}")"; then
  full_deploy_reason="检测到部署入口相关变更：${full_deploy_reason}"
fi

if [[ -z "${full_deploy_reason}" ]]; then
  backend_change_reason="$(changed_files_match "${changed_files}" "${BACKEND_CHANGE_PATTERNS[@]}")" || true
  frontend_change_reason="$(changed_files_match "${changed_files}" "${FRONTEND_CHANGE_PATTERNS[@]}")" || true
fi

build_services=()
deploy_services=()
if [[ -n "${full_deploy_reason}" ]]; then
  log "${full_deploy_reason}"
  build_services=(backend frontend)
  deploy_services=("${APP_SERVICES[@]}")
else
  if [[ -n "${backend_change_reason}" ]]; then
    log "检测到后端相关变更：${backend_change_reason}"
    build_services+=(backend)
    deploy_services+=("${BACKEND_SERVICES[@]}")
  fi
  if [[ -n "${frontend_change_reason}" ]]; then
    log "检测到前端相关变更：${frontend_change_reason}"
    build_services+=(frontend)
    deploy_services+=("${FRONTEND_SERVICES[@]}")
  fi
fi

if [[ ${NO_CACHE} -eq 1 && ${#build_services[@]} -eq 0 ]]; then
  log "按 --no-cache 要求执行全量应用构建"
  build_services=(backend frontend)
  deploy_services=("${APP_SERVICES[@]}")
fi

db_change_reason="$(db_changes_between_revisions "${old_revision_full}" "${new_revision_full}")" || true

if [[ ${SKIP_BACKUP} -eq 0 ]]; then
  backup_reason=""
  if [[ ${FORCE_BACKUP} -eq 1 ]]; then
    backup_reason="按 --force-backup 要求强制备份"
  elif [[ -n "${db_change_reason}" ]]; then
    backup_reason="检测到数据库相关变更：${db_change_reason}"
  fi

  if [[ -n "${backup_reason}" ]]; then
    log "${backup_reason}"
    log "备份前确保基础服务正在运行：${BASE_SERVICES[*]}"
    compose up -d "${BASE_SERVICES[@]}"
    run_container_backup
  else
    log "未检测到数据库相关变更，自动跳过部署前数据库备份；如需备份请使用 --force-backup"
  fi
else
  log "按要求跳过数据库备份"
fi

build_args=()
if [[ ${NO_CACHE} -eq 1 ]]; then
  build_args+=(--no-cache)
fi

if [[ ${#build_services[@]} -gt 0 ]]; then
  log "构建生产镜像：$(join_by_space "${build_services[@]}")"
  compose build "${build_args[@]}" "${build_services[@]}"
else
  log "未检测到后端或前端运行时变更，跳过镜像构建"
fi

if [[ ${#deploy_services[@]} -gt 0 ]]; then
  log "确保基础服务正在运行：${BASE_SERVICES[*]}"
  compose up -d "${BASE_SERVICES[@]}"
fi

if [[ ${SKIP_MIGRATE} -eq 0 && -n "${db_change_reason}" ]]; then
  log "执行数据库迁移"
  if [[ ${#deploy_services[@]} -eq 0 ]]; then
    log "数据库相关变更未触发应用重建，先确保基础服务正在运行"
    compose up -d "${BASE_SERVICES[@]}"
  fi
  compose run --rm backend alembic upgrade head
else
  if [[ ${SKIP_MIGRATE} -eq 1 ]]; then
    log "按要求跳过数据库迁移"
  else
    log "未检测到数据库相关变更，跳过数据库迁移"
  fi
fi

if [[ ${#deploy_services[@]} -gt 0 ]]; then
  log "重建已更新的应用服务：$(join_by_space "${deploy_services[@]}")"
  compose up -d --no-deps "${deploy_services[@]}"
else
  log "未检测到需要重建的应用服务"
fi

wait_for_url "backend" "${BACKEND_HEALTH_URL}" 40 3
wait_for_url "frontend" "${FRONTEND_HEALTH_URL}" 30 3

log "当前服务状态"
compose ps

if [[ ${PRUNE} -eq 1 ]]; then
  log "清理悬空 Docker 镜像"
  docker image prune -f
fi

log "部署完成：${old_revision} -> ${new_revision}"
