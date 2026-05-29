#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${ENV_FILE:-.env}"
ENV_EXAMPLE="${ENV_EXAMPLE:-.env.example}"
CUSTOMER_ID=""
FORCE=false

usage() {
  cat <<'EOF'
Usage: ./prepare-go-live-env.sh [--customer-id <id>] [--env-file .env] [--force]

Generate production-safe random values for SagittaDB Enterprise customer
deployments. Existing non-placeholder values are preserved unless --force is
provided.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --customer-id)
      CUSTOMER_ID="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
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

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  [[ -f "$ENV_EXAMPLE" ]] || {
    echo "Missing $ENV_FILE and $ENV_EXAMPLE" >&2
    exit 1
  }
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from $ENV_EXAMPLE"
fi

CUSTOMER_ID="$CUSTOMER_ID" FORCE="$FORCE" ENV_FILE="$ENV_FILE" python3 - <<'PY'
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

env_file = Path(os.environ["ENV_FILE"])
customer_id = os.environ.get("CUSTOMER_ID", "").strip()
force = os.environ.get("FORCE") == "true"

random_values = {
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(36),
    "REDIS_PASSWORD": lambda: secrets.token_urlsafe(36),
    "SECRET_KEY": lambda: base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("="),
    "LICENSE_DEPLOYMENT_ID": lambda: "sagittadb-" + secrets.token_hex(16),
}

placeholder_prefixes = ("CHANGE_ME", "")
lines = env_file.read_text(encoding="utf-8").splitlines()
seen: set[str] = set()
updated: list[str] = []


def should_replace(value: str) -> bool:
    return force or value.strip() in placeholder_prefixes or value.strip().startswith("CHANGE_ME")


for index, line in enumerate(lines):
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    seen.add(key)
    if key in random_values and should_replace(value):
        lines[index] = f"{key}={random_values[key]()}"
        updated.append(key)
    elif key == "LICENSE_CUSTOMER_ID" and customer_id and should_replace(value):
        lines[index] = f"{key}={customer_id}"
        updated.append(key)

for key, factory in random_values.items():
    if key not in seen:
        lines.append(f"{key}={factory()}")
        updated.append(key)

if customer_id and "LICENSE_CUSTOMER_ID" not in seen:
    lines.append(f"LICENSE_CUSTOMER_ID={customer_id}")
    updated.append("LICENSE_CUSTOMER_ID")

env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

if updated:
    print("Updated keys: " + ", ".join(sorted(set(updated))))
else:
    print("No changes. Existing production values were preserved.")
PY

echo "Environment prepared: $ENV_FILE"
echo "Keep SECRET_KEY and LICENSE_DEPLOYMENT_ID stable across upgrades."
