#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

failures=0
warnings=0

info() { printf '[INFO] %s\n' "$*"; }
pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; failures=$((failures + 1)); }

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

env_value() {
  local key="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    return 1
  fi
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | sed -E "s/^${key}=//; s/^['\"]//; s/['\"]$//"
}

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "命令可用: $1"
  else
    fail "缺少命令: $1"
  fi
}

check_http() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -k -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  if [[ "$code" =~ ^2|3 ]]; then
    pass "$name 可访问: $url ($code)"
  else
    fail "$name 不可访问: $url ($code)"
  fi
}

check_compose_service() {
  local service="$1"
  local status
  status="$(compose ps "$service" --format json 2>/dev/null | tr -d '\n' || true)"
  if [[ -z "$status" ]]; then
    fail "Compose 服务不存在或未启动: $service"
    return
  fi
  if grep -qi '"State":"running"' <<<"$status"; then
    pass "Compose 服务运行中: $service"
  else
    fail "Compose 服务未运行: $service"
  fi
  if grep -qi '"Health":"healthy"' <<<"$status"; then
    pass "Compose 服务健康: $service"
  elif grep -qi '"Health":""' <<<"$status"; then
    warn "Compose 服务未配置健康检查: $service"
  else
    warn "Compose 服务健康状态非 healthy: $service"
  fi
}

check_env_secret() {
  local key="$1"
  local default_value="$2"
  local value
  value="$(env_value "$key" || true)"
  if [[ -z "$value" ]]; then
    warn "$key 未在 $ENV_FILE 中显式配置"
  elif [[ "$value" == "$default_value" ]]; then
    fail "$key 仍使用默认值"
  else
    pass "$key 已配置且不是默认值"
  fi
}

check_port_not_public() {
  local port="$1"
  local name="$2"
  local output
  output="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$output" ]]; then
    pass "$name 未监听宿主机端口 ${port}"
    return
  fi
  if grep -E "(\*:|0\.0\.0\.0:|\[::\]:)${port}" <<<"$output" >/dev/null; then
    warn "$name 正在监听所有地址端口 ${port}，请确认仅限内网或防火墙保护"
  else
    pass "$name 端口 ${port} 未对所有地址监听"
  fi
}

info "Sagitta Control 部署前预检开始"
info "ROOT_DIR=$ROOT_DIR"
info "COMPOSE_FILE=$COMPOSE_FILE"
info "API_BASE_URL=$API_BASE_URL"
info "FRONTEND_URL=$FRONTEND_URL"

check_command docker
check_command curl

if [[ ! -f "$ENV_FILE" ]]; then
  warn "未找到环境文件: $ENV_FILE"
else
  pass "环境文件存在: $ENV_FILE"
fi

for service in postgres redis backend celery_worker celery_beat frontend; do
  check_compose_service "$service"
done

check_http "后端健康检查" "$API_BASE_URL/health"
check_http "前端入口" "$FRONTEND_URL/"

if compose exec -T backend alembic current >/tmp/sagitta-control-alembic-current.txt 2>&1; then
  pass "Alembic current 可执行"
  if compose exec -T backend alembic heads >/tmp/sagitta-control-alembic-heads.txt 2>&1; then
    current="$(grep -E '^[0-9]{4}_[a-zA-Z0-9_]+' /tmp/sagitta-control-alembic-current.txt | awk '{print $1}' | tail -n 1)"
    head="$(grep -E '^[0-9]{4}_[a-zA-Z0-9_]+' /tmp/sagitta-control-alembic-heads.txt | awk '{print $1}' | tail -n 1)"
    if [[ -n "$current" && -n "$head" && "$current" == "$head" ]]; then
      pass "Alembic 已在 head: $head"
    else
      warn "Alembic current 与 head 可能不一致: current=${current:-unknown}, head=${head:-unknown}"
    fi
  fi
else
  fail "Alembic current 执行失败"
fi

if compose exec -T celery_worker celery -A app.celery_app inspect ping >/tmp/sagitta-control-celery-ping.txt 2>&1; then
  pass "Celery worker ping 正常"
else
  fail "Celery worker ping 失败"
fi

check_env_secret SECRET_KEY CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS
check_env_secret POSTGRES_PASSWORD sagitta123
check_env_secret REDIS_PASSWORD redis123

license_public_key="$(env_value LICENSE_PUBLIC_KEY || true)"
license_server_url="$(env_value LICENSE_SERVER_URL || true)"
license_online_grace_days="$(env_value LICENSE_ONLINE_GRACE_DAYS || true)"
integrity_required="$(env_value APP_INTEGRITY_REQUIRED || true)"
integrity_manifest="$(env_value APP_INTEGRITY_MANIFEST || true)"
if [[ -z "$license_public_key" ]]; then
  warn "LICENSE_PUBLIC_KEY 未配置，离线/在线正式 License 验签将不可用"
else
  pass "LICENSE_PUBLIC_KEY 已配置"
fi
if [[ -n "$license_server_url" ]]; then
  pass "LICENSE_SERVER_URL 已配置: $license_server_url"
else
  warn "LICENSE_SERVER_URL 未配置；在线激活/刷新不可用，离线导入仍可使用"
fi
if [[ "${license_online_grace_days:-7}" =~ ^[0-9]+$ ]] && (( ${license_online_grace_days:-7} > 0 )); then
  pass "LICENSE_ONLINE_GRACE_DAYS=${license_online_grace_days:-7}"
else
  warn "LICENSE_ONLINE_GRACE_DAYS 未设置为正整数；在线授权离线缓存可能不会 fail closed"
fi
if [[ "$integrity_required" == "true" ]]; then
  pass "APP_INTEGRITY_REQUIRED 已启用"
  if compose exec -T backend test -f "${integrity_manifest:-/app/COMMERCIAL-MANIFEST.json}" >/dev/null 2>&1; then
    pass "商业完整性 Manifest 存在"
  else
    fail "商业完整性 Manifest 不存在: ${integrity_manifest:-/app/COMMERCIAL-MANIFEST.json}"
  fi
else
  warn "APP_INTEGRITY_REQUIRED 未启用；商业镜像防篡改启动校验未强制执行"
fi

check_port_not_public 5432 PostgreSQL
check_port_not_public 6379 Redis
check_port_not_public 5555 Flower
check_port_not_public 9090 Prometheus
check_port_not_public 3000 Grafana

printf '\n预检完成：%s 个失败，%s 个警告。\n' "$failures" "$warnings"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
