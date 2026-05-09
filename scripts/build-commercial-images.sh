#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
MANIFEST_PRIVATE_KEY_FILE="${MANIFEST_PRIVATE_KEY_FILE:?MANIFEST_PRIVATE_KEY_FILE is required}"

docker build \
  -f backend/Dockerfile.commercial \
  --secret id=manifest_private_key,src="${MANIFEST_PRIVATE_KEY_FILE}" \
  --build-arg SAGITTADB_VERSION="${VERSION}" \
  -t "${IMAGE_REPOSITORY}-backend:${VERSION}" \
  .

docker build \
  -f frontend/Dockerfile \
  -t "${IMAGE_REPOSITORY}-frontend:${VERSION}" \
  frontend
