#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagitta-control}"
PULL_IMAGES="${PULL_IMAGES:-true}"
EXPECTED_PLATFORMS="${EXPECTED_PLATFORMS:-linux/amd64}"

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

validate_manifest_platforms() {
  local image="$1"
  if [[ "${PULL_IMAGES}" != "true" || -z "${EXPECTED_PLATFORMS}" ]]; then
    return
  fi

  docker manifest inspect --verbose "${image}" >"${tmpdir}/manifest.json"
  set +e
  EXPECTED_PLATFORMS="${EXPECTED_PLATFORMS}" python3 - "${image}" "${tmpdir}/manifest.json" <<'PY'
from __future__ import annotations

import json
import os
import sys

image = sys.argv[1]
manifest_payload = json.loads(open(sys.argv[2], encoding="utf-8").read())
expected = {item.strip() for item in os.environ["EXPECTED_PLATFORMS"].split(",") if item.strip()}

platforms: set[str] = set()
manifests = manifest_payload if isinstance(manifest_payload, list) else [manifest_payload]
for manifest in manifests:
    for item in manifest.get("manifests", []):
        platform = item.get("platform") or {}
        os_name = platform.get("os")
        arch = platform.get("architecture")
        variant = platform.get("variant")
        if os_name and arch:
            value = f"{os_name}/{arch}"
            if variant:
                value += f"/{variant}"
            platforms.add(value)

    descriptor_platform = (manifest.get("Descriptor") or {}).get("platform") or {}
    os_name = descriptor_platform.get("os")
    arch = descriptor_platform.get("architecture")
    variant = descriptor_platform.get("variant")
    if os_name and arch:
        value = f"{os_name}/{arch}"
        if variant:
            value += f"/{variant}"
        platforms.add(value)

    if manifest.get("architecture") and manifest.get("os"):
        platforms.add(f"{manifest['os']}/{manifest['architecture']}")

if not platforms:
    sys.exit(2)

missing = expected - platforms
if missing:
    print(
        f"{image} is missing required platform(s): {', '.join(sorted(missing))}. "
        f"Published platform(s): {', '.join(sorted(platforms)) or '<none>'}.",
        file=sys.stderr,
    )
    sys.exit(1)
PY
  local status="$?"
  set -e

  if [[ "${status}" == "0" ]]; then
    return
  fi
  if [[ "${status}" != "2" ]]; then
    return "${status}"
  fi

  docker pull "${image}" >/dev/null
  local local_platform
  local_platform="$(docker image inspect \
    --format '{{.Os}}/{{.Architecture}}{{if .Variant}}/{{.Variant}}{{end}}' \
    "${image}")"
  EXPECTED_PLATFORMS="${EXPECTED_PLATFORMS}" python3 - "${image}" "${local_platform}" <<'PY'
from __future__ import annotations

import os
import sys

image = sys.argv[1]
platform = sys.argv[2].strip()
expected = {item.strip() for item in os.environ["EXPECTED_PLATFORMS"].split(",") if item.strip()}

if platform not in expected:
    print(
        f"{image} is missing required platform(s): {', '.join(sorted(expected - {platform}))}. "
        f"Published platform(s): {platform or '<none>'}.",
        file=sys.stderr,
    )
    sys.exit(1)
PY
}

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
  if grep -RInE '^[[:space:]]*(//|/\*)[#@][[:space:]]*sourceMappingURL=' \
    "${rootfs}/usr/share/nginx/html" >/dev/null; then
    echo "Commercial frontend image contains sourcemap directive references." >&2
    exit 1
  fi
}

backend_image="${IMAGE_REPOSITORY}-backend:${VERSION}"
frontend_image="${IMAGE_REPOSITORY}-frontend:${VERSION}"

validate_manifest_platforms "${backend_image}"
validate_manifest_platforms "${frontend_image}"
validate_backend "${backend_image}"
validate_frontend "${frontend_image}"

echo "用户部署镜像已通过校验：${IMAGE_REPOSITORY}: ${VERSION}"
