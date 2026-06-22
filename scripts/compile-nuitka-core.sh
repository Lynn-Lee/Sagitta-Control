#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
OUTPUT_DIR="${NUITKA_OUTPUT_DIR:-/tmp/sagitta-control-nuitka}"
MODULES="${NUITKA_MODULES:-}"

cd "${ROOT_DIR}"
mkdir -p "${OUTPUT_DIR}"

if [[ -z "${MODULES}" ]]; then
  MODULES="$(
    find app -type f -name '*.py' ! -name '__init__.py' \
      | LC_ALL=C sort
  )"
fi

for module in ${MODULES}; do
  [[ -f "${module}" ]] || {
    echo "未找到 Nuitka 编译模块：${module}" >&2
    exit 1
  }
  echo "正在编译 ${module}"
  module_output_dir="${OUTPUT_DIR}/$(printf '%s' "${module}" | tr '/.' '__')"
  rm -rf "${module_output_dir}"
  mkdir -p "${module_output_dir}"
  python -m nuitka \
    --module "${module}" \
    --output-dir="${module_output_dir}" \
    --no-pyi-file \
    --remove-output

  base="$(basename "${module}" .py)"
  target_dir="$(dirname "${module}")"
  compiled="$(find "${module_output_dir}" -maxdepth 1 -type f -name "${base}.*.so" | head -n 1)"
  [[ -n "${compiled}" ]] || {
    echo "未找到编译后的扩展模块：${module}" >&2
    exit 1
  }
  cp "${compiled}" "${target_dir}/"
  rm -rf "${module_output_dir}"
  rm -f "${module}"
done
