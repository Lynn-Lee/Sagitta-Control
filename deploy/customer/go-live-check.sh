#!/usr/bin/env bash
set -Eeuo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1}"
ENV_FILE="${ENV_FILE:-.env}"
TOKEN="${TOKEN:-}"
USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"
TIMEOUT="${TIMEOUT:-10}"

failures=0
warnings=0
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

usage() {
  cat <<'EOF'
Usage: ./go-live-check.sh [options]

Options:
  --api-base-url <url>   Backend base URL, default http://127.0.0.1:8000
  --frontend-url <url>   Frontend URL, default http://127.0.0.1
  --env-file <path>      Environment file, default .env
  --token <token>        Admin access token with system_config_manage permission
  --username <name>      Admin username, used when --token is not provided
  --password <password>  Admin password, used when --token is not provided

The check is intentionally strict for production go-live: trial License,
missing customer ID, missing active instance, incomplete onboarding, failed
monitor collection, or any readiness action item will fail.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base-url)
      API_BASE_URL="${2:-}"
      shift 2
      ;;
    --frontend-url)
      FRONTEND_URL="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2
      ;;
    --username)
      USERNAME="${2:-}"
      shift 2
      ;;
    --password)
      PASSWORD="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; failures=$((failures + 1)); }

require_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "python3 or python is required" >&2
    exit 1
  fi
}

env_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 1
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | sed -E "s/^${key}=//; s/^['\"]//; s/['\"]$//"
}

check_required_env() {
  local key="$1"
  local value
  value="$(env_value "$key" || true)"
  if [[ -z "$value" ]]; then
    fail "$key 未配置"
  elif [[ "$value" == CHANGE_ME* ]]; then
    fail "$key 仍是占位符"
  else
    pass "$key 已配置"
  fi
}

check_exact_env() {
  local key="$1"
  local expected="$2"
  local value
  value="$(env_value "$key" || true)"
  if [[ "$value" == "$expected" ]]; then
    pass "$key=$expected"
  else
    fail "$key 必须为 $expected，当前为 ${value:-<empty>}"
  fi
}

http_code() {
  local url="$1"
  curl -k -sS --max-time "$TIMEOUT" -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true
}

api_request() {
  local method="$1"
  local path="$2"
  local out="$3"
  local body="${4:-}"
  local headers=(-H "Accept: application/json")
  if [[ -n "$TOKEN" ]]; then
    headers+=(-H "Authorization: Bearer $TOKEN")
  fi
  if [[ -n "$body" ]]; then
    headers+=(-H "Content-Type: application/json")
    curl -k -sS --max-time "$TIMEOUT" -X "$method" "${headers[@]}" -d "$body" \
      -o "$out" -w '%{http_code}' "${API_BASE_URL%/}${path}" 2>/dev/null || true
  else
    curl -k -sS --max-time "$TIMEOUT" -X "$method" "${headers[@]}" \
      -o "$out" -w '%{http_code}' "${API_BASE_URL%/}${path}" 2>/dev/null || true
  fi
}

json_get() {
  local file="$1"
  local expr="$2"
  "$PYTHON_BIN" - "$file" "$expr" <<'PY'
from __future__ import annotations

import json
import sys

data = json.loads(open(sys.argv[1], encoding="utf-8").read() or "{}")
value = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
elif value is None:
    print("")
else:
    print(value)
PY
}

login_if_needed() {
  if [[ -n "$TOKEN" ]]; then
    return
  fi
  if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
    fail "缺少 --token，或 --username/--password；无法执行客户上线运行态检查"
    return
  fi

  local body login_out code token change_required requires_2fa
  login_out="$tmp_dir/login.json"
  body="$("$PYTHON_BIN" - "$USERNAME" "$PASSWORD" <<'PY'
import json
import sys
print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}, ensure_ascii=False))
PY
)"
  code="$(api_request POST /api/v1/auth/login/ "$login_out" "$body")"
  if [[ "$code" != "200" ]]; then
    fail "管理员登录失败：HTTP $code $(cat "$login_out")"
    return
  fi
  change_required="$(json_get "$login_out" password_change_required)"
  requires_2fa="$(json_get "$login_out" requires_2fa)"
  if [[ "$change_required" == "True" || "$change_required" == "true" ]]; then
    fail "管理员账号仍要求修改初始密码"
    return
  fi
  if [[ "$requires_2fa" == "True" || "$requires_2fa" == "true" ]]; then
    fail "管理员账号启用了 2FA；请改用 --token 执行上线检查"
    return
  fi
  token="$(json_get "$login_out" access_token)"
  if [[ -z "$token" ]]; then
    fail "管理员登录未返回 access_token"
    return
  fi
  TOKEN="$token"
  pass "管理员认证通过"
}

check_json_equals() {
  local file="$1"
  local expr="$2"
  local expected="$3"
  local label="$4"
  local value
  value="$(json_get "$file" "$expr")"
  if [[ "$value" == "$expected" ]]; then
    pass "$label"
  else
    fail "$label：期望 $expected，实际 ${value:-<empty>}"
  fi
}

check_json_nonempty() {
  local file="$1"
  local expr="$2"
  local label="$3"
  local value
  value="$(json_get "$file" "$expr")"
  if [[ -n "$value" ]]; then
    pass "$label"
  else
    fail "$label"
  fi
}

require_python

printf '[INFO] Sagitta Control go-live check\n'
printf '[INFO] API_BASE_URL=%s\n' "$API_BASE_URL"
printf '[INFO] FRONTEND_URL=%s\n' "$FRONTEND_URL"
printf '[INFO] ENV_FILE=%s\n' "$ENV_FILE"

[[ -f "$ENV_FILE" ]] && pass "环境文件存在" || fail "环境文件不存在: $ENV_FILE"

for key in POSTGRES_PASSWORD REDIS_PASSWORD SECRET_KEY LICENSE_PUBLIC_KEY LICENSE_CUSTOMER_ID LICENSE_SERVER_URL LICENSE_DEPLOYMENT_ID MANIFEST_PUBLIC_KEY; do
  check_required_env "$key"
done
check_exact_env APP_ENV production
check_exact_env APP_INTEGRITY_REQUIRED true
check_exact_env LICENSE_ALLOW_LEGACY_LICENSE_IMPORT false

secret_key="$(env_value SECRET_KEY || true)"
if [[ ${#secret_key} -ge 32 && "$secret_key" != "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS" ]]; then
  pass "SECRET_KEY 长度满足生产要求"
else
  fail "SECRET_KEY 长度不足或仍为默认值"
fi

grace_days="$(env_value LICENSE_ONLINE_GRACE_DAYS || true)"
if [[ "$grace_days" =~ ^[0-9]+$ ]] && (( grace_days > 0 && grace_days <= 7 )); then
  pass "LICENSE_ONLINE_GRACE_DAYS=$grace_days"
else
  fail "LICENSE_ONLINE_GRACE_DAYS 必须是 1-7 的正整数"
fi

api_health_code="$(http_code "${API_BASE_URL%/}/health")"
[[ "$api_health_code" =~ ^[23] ]] && pass "后端健康检查可访问" || fail "后端健康检查不可访问：HTTP ${api_health_code:-000}"

frontend_code="$(http_code "$FRONTEND_URL")"
[[ "$frontend_code" =~ ^[23] ]] && pass "前端入口可访问" || fail "前端入口不可访问：HTTP ${frontend_code:-000}"

login_if_needed

if [[ -n "$TOKEN" ]]; then
  about_json="$tmp_dir/about.json"
  code="$(api_request GET /api/v1/system/support/about "$about_json")"
  if [[ "$code" == "200" ]]; then
    pass "商业支持状态接口可访问"
    check_json_equals "$about_json" project_code sagitta-control "授权项目码为 sagitta-control"
    check_json_equals "$about_json" license.status licensed "License 为正式授权"
    check_json_equals "$about_json" license.is_trial False "License 非试用"
    check_json_nonempty "$about_json" license.activation_customer_id "正式激活客户 ID 已生成"
    check_json_nonempty "$about_json" license.activation_deployment_fingerprint "正式激活部署指纹已生成"
    check_json_equals "$about_json" readiness.status ready "推广就绪度为 ready"
    check_json_equals "$about_json" readiness.conclusion 可推广 "推广结论为可推广"
    check_json_equals "$about_json" runtime.health ok "运行状态健康"
    check_json_equals "$about_json" runtime.failed_monitor_collect_configs 0 "监控采集无失败配置"

    active_instances="$(json_get "$about_json" usage.active_instances)"
    if [[ "$active_instances" =~ ^[0-9]+$ ]] && (( active_instances > 0 )); then
      pass "至少一个活跃实例"
    else
      fail "缺少活跃实例"
    fi

    active_users="$(json_get "$about_json" usage.active_users)"
    if [[ "$active_users" =~ ^[0-9]+$ ]] && (( active_users > 0 )); then
      pass "至少一个活跃用户"
    else
      fail "缺少活跃用户"
    fi

    env_customer_id="$(env_value LICENSE_CUSTOMER_ID || true)"
    runtime_customer_id="$(json_get "$about_json" license.activation_customer_id)"
    if [[ -n "$runtime_customer_id" && "$runtime_customer_id" == "$env_customer_id" ]]; then
      pass "运行态客户 ID 与 .env 一致"
    else
      fail "运行态客户 ID 与 .env 不一致：env=${env_customer_id:-<empty>}, runtime=${runtime_customer_id:-<empty>}"
    fi

    action_items="$(json_get "$about_json" readiness.action_items)"
    if [[ "$action_items" == "[]" ]]; then
      pass "无推广前待处理项"
    else
      fail "仍存在推广前待处理项：$action_items"
    fi
  else
    fail "商业支持状态接口不可访问：HTTP $code $(cat "$about_json")"
  fi

  onboarding_json="$tmp_dir/onboarding.json"
  code="$(api_request GET /api/v1/system/onboarding/status "$onboarding_json")"
  if [[ "$code" == "200" ]]; then
    check_json_equals "$onboarding_json" is_complete True "实施交付向导已完成"
  else
    fail "实施交付向导状态接口不可访问：HTTP $code $(cat "$onboarding_json")"
  fi
fi

printf '\nGo-live check completed: %s failure(s), %s warning(s).\n' "$failures" "$warnings"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
