#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
PULL_IMAGES="${PULL_IMAGES:-true}"

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

validate_backend() {
  local image="$1"
  local cid rootfs
  rootfs="${tmpdir}/backend-rootfs"
  mkdir -p "${rootfs}"
  [[ "${PULL_IMAGES}" != "true" ]] || docker pull "${image}" >/dev/null
  cid="$(docker create "${image}")"
  docker export "${cid}" | tar -C "${rootfs}" -xf -
  docker rm "${cid}" >/dev/null

  COMMERCIAL_APP_DIR="${rootfs}/app/app" ROOT_DIR="${rootfs}/app" \
    "$(dirname "$0")/validate-commercial-image-tree.sh"

  if find "${rootfs}/app" -type f \( -name '*.pyc' -o -name '*.pyo' \) | grep -q .; then
    echo "Commercial backend image contains Python bytecode cache files." >&2
    exit 1
  fi

  if [[ ! -f "${rootfs}/app/COMMERCIAL-MANIFEST.json" ]]; then
    echo "Commercial backend image is missing /app/COMMERCIAL-MANIFEST.json" >&2
    exit 1
  fi
}

validate_frontend() {
  local image="$1"
  local cid rootfs
  rootfs="${tmpdir}/frontend-rootfs"
  mkdir -p "${rootfs}"
  [[ "${PULL_IMAGES}" != "true" ]] || docker pull "${image}" >/dev/null
  cid="$(docker create "${image}")"
  docker export "${cid}" | tar -C "${rootfs}" -xf -
  docker rm "${cid}" >/dev/null

  if find "${rootfs}/usr/share/nginx/html" -type f -name '*.map' | grep -q .; then
    echo "Commercial frontend image contains sourcemap files." >&2
    exit 1
  fi
  if grep -R "sourceMappingURL" "${rootfs}/usr/share/nginx/html" >/dev/null; then
    echo "Commercial frontend image contains sourceMappingURL references." >&2
    exit 1
  fi
}

validate_backend "${IMAGE_REPOSITORY}-backend:${VERSION}"
validate_frontend "${IMAGE_REPOSITORY}-frontend:${VERSION}"

echo "Commercial image validation passed for ${IMAGE_REPOSITORY}: ${VERSION}"
