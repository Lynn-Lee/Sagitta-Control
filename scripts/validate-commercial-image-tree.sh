#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${ROOT_DIR:-/app}"
APP_DIR="${COMMERCIAL_APP_DIR:-${ROOT_DIR}/app}"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "未找到商业应用目录：${APP_DIR}" >&2
  exit 1
fi

source_files="$(find "${APP_DIR}" -type f -name '*.py' ! -name '__init__.py' | LC_ALL=C sort)"

if [[ -n "${source_files}" ]]; then
  echo "商业镜像不得包含后端 Python 源码文件：" >&2
  printf '%s\n' "${source_files}" | sed 's/^/  /' >&2
  exit 1
fi

bytecode_files="$(find "${APP_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' \) | LC_ALL=C sort)"

if [[ -n "${bytecode_files}" ]]; then
  echo "商业镜像不得包含 Python 字节码缓存文件：" >&2
  printf '%s\n' "${bytecode_files}" | sed 's/^/  /' >&2
  exit 1
fi

echo "商业后端目录校验通过：${APP_DIR}"
