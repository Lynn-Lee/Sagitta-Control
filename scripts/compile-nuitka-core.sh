#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
OUTPUT_DIR="${NUITKA_OUTPUT_DIR:-/tmp/sagittadb-nuitka}"
MODULES="${NUITKA_MODULES:-app/services/license.py app/core/security.py app/core/deps.py app/services/user.py app/services/instance.py}"

cd "${ROOT_DIR}"
mkdir -p "${OUTPUT_DIR}"

for module in ${MODULES}; do
  [[ -f "${module}" ]] || {
    echo "Nuitka module not found: ${module}" >&2
    exit 1
  }
  echo "Compiling ${module}"
  python -m nuitka \
    --module "${module}" \
    --output-dir="${OUTPUT_DIR}" \
    --no-pyi-file \
    --remove-output

  base="$(basename "${module}" .py)"
  target_dir="$(dirname "${module}")"
  compiled="$(find "${OUTPUT_DIR}" -maxdepth 1 -type f -name "${base}.*.so" | head -n 1)"
  [[ -n "${compiled}" ]] || {
    echo "Compiled extension not found for ${module}" >&2
    exit 1
  }
  cp "${compiled}" "${target_dir}/"
  rm -f "${module}"
done
