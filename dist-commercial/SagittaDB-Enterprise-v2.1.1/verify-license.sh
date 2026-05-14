#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
USERNAME="${SAGITTADB_ADMIN_USERNAME:-admin}"
PASSWORD="${SAGITTADB_ADMIN_PASSWORD:-Admin@2024!}"
ACTIVATION_CODE="${1:-${ACTIVATION_CODE:-}}"
CUSTOMER_ID="${2:-${LICENSE_CUSTOMER_ID:-}}"

die() {
  echo "错误：$*" >&2
  exit 1
}

[[ -n "$ACTIVATION_CODE" ]] || die "需要通过第一个参数或 ACTIVATION_CODE 提供激活码"
[[ -n "$CUSTOMER_ID" ]] || die "需要通过第二个参数或 LICENSE_CUSTOMER_ID 提供客户 ID"

TOKEN="$(
  curl -fsS -X POST "$API_BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("access_token") or data.get("token") or data.get("data",{}).get("access_token",""))'
)"
[[ -n "$TOKEN" ]] || die "登录失败或响应中缺少 token"

auth_curl() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$@"
}

echo "1. 当前 License 状态"
auth_curl "$API_BASE/system/license/status"
echo

echo "2. 在线激活 License"
auth_curl -X POST "$API_BASE/system/license/activate" \
  -H 'Content-Type: application/json' \
  -d "{\"activation_code\":\"$ACTIVATION_CODE\",\"customer_id\":\"$CUSTOMER_ID\"}"
echo

echo "3. 生成离线 Challenge"
auth_curl -X POST "$API_BASE/system/license/challenge" \
  -H 'Content-Type: application/json' \
  -d "{\"customer_id\":\"$CUSTOMER_ID\"}"
echo

echo "4. 联网刷新 License"
auth_curl -X POST "$API_BASE/system/license/refresh"
echo

echo "5. 最终 License 状态"
auth_curl "$API_BASE/system/license/status"
echo
