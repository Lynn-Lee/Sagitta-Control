#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
USERNAME="${SAGITTADB_ADMIN_USERNAME:-admin}"
PASSWORD="${SAGITTADB_ADMIN_PASSWORD:-Admin@2024!}"
ACTIVATION_CODE="${1:-${ACTIVATION_CODE:-}}"
CUSTOMER_ID="${2:-${LICENSE_CUSTOMER_ID:-}}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -n "$ACTIVATION_CODE" ]] || die "activation code is required as arg1 or ACTIVATION_CODE"
[[ -n "$CUSTOMER_ID" ]] || die "customer id is required as arg2 or LICENSE_CUSTOMER_ID"

TOKEN="$(
  curl -fsS -X POST "$API_BASE/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("access_token") or data.get("token") or data.get("data",{}).get("access_token",""))'
)"
[[ -n "$TOKEN" ]] || die "login failed or token missing"

auth_curl() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$@"
}

echo "1. Current license status"
auth_curl "$API_BASE/system/license/status"
echo

echo "2. Activate online license"
auth_curl -X POST "$API_BASE/system/license/activate" \
  -H 'Content-Type: application/json' \
  -d "{\"activation_code\":\"$ACTIVATION_CODE\",\"customer_id\":\"$CUSTOMER_ID\"}"
echo

echo "3. 生成离线 Challenge"
auth_curl -X POST "$API_BASE/system/license/challenge" \
  -H 'Content-Type: application/json' \
  -d "{\"customer_id\":\"$CUSTOMER_ID\"}"
echo

echo "4. Refresh online license"
auth_curl -X POST "$API_BASE/system/license/refresh"
echo

echo "5. Final license status"
auth_curl "$API_BASE/system/license/status"
echo
