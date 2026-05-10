#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DOCKERIGNORE="${ROOT_DIR}/.dockerignore"

[[ -f "${DOCKERIGNORE}" ]] || {
  echo "Missing root .dockerignore for commercial root-context builds" >&2
  exit 1
}

required_patterns=(
  ".env"
  ".env.*"
  "*PRIVATE_KEY*"
  "*private_key*"
  "*license*.json"
  "backend/.venv/"
  "backend/tests/"
  "backend/downloads/"
  "frontend/node_modules/"
  "frontend/dist/"
  "dist-commercial/"
)

for pattern in "${required_patterns[@]}"; do
  if ! grep -Fxq "${pattern}" "${DOCKERIGNORE}"; then
    echo "Root .dockerignore missing required commercial context exclusion: ${pattern}" >&2
    exit 1
  fi
done

for path in \
  "${ROOT_DIR}/backend/.venv" \
  "${ROOT_DIR}/frontend/node_modules" \
  "${ROOT_DIR}/dist-commercial"; do
  if [[ -e "${path}" ]]; then
    relative="${path#${ROOT_DIR}/}"
    if ! grep -Fxq "${relative}/" "${DOCKERIGNORE}"; then
      echo "Existing high-risk build context path is not excluded: ${relative}" >&2
      exit 1
    fi
  fi
done

echo "Commercial build context guard passed"
