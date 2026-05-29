#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
MANIFEST_PRIVATE_KEY_FILE="${MANIFEST_PRIVATE_KEY_FILE:?MANIFEST_PRIVATE_KEY_FILE is required}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

docker build \
  --platform "${DOCKER_PLATFORM}" \
  -f backend/Dockerfile.commercial \
  --secret id=manifest_private_key,src="${MANIFEST_PRIVATE_KEY_FILE}" \
  --build-arg SAGITTADB_VERSION="${VERSION}" \
  --build-arg PIP_INDEX_URL="${PIP_INDEX_URL}" \
  --build-arg PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" \
  -t "${IMAGE_REPOSITORY}-backend:${VERSION}" \
  .

docker build \
  --platform "${DOCKER_PLATFORM}" \
  -f frontend/Dockerfile \
  -t "${IMAGE_REPOSITORY}-frontend:${VERSION}" \
  frontend
