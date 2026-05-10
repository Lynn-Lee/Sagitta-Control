#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
OUTPUT_DIR="${SBOM_OUTPUT_DIR:-dist-commercial/sbom}"

command -v syft >/dev/null 2>&1 || {
  echo "syft is required to generate SBOM files" >&2
  exit 1
}

mkdir -p "${OUTPUT_DIR}"

write_sha256() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${path}" > "${path}.sha256"
  else
    shasum -a 256 "${path}" > "${path}.sha256"
  fi
}

for component in backend frontend; do
  image="${IMAGE_REPOSITORY}-${component}:${VERSION}"
  out="${OUTPUT_DIR}/sagittadb-${component}-${VERSION}.cyclonedx.json"
  syft "${image}" -o cyclonedx-json="${out}"
  write_sha256 "${out}"
  echo "SBOM generated: ${out}"
done
