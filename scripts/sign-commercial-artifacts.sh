#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.0.0}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
PACKAGE_ZIP="${PACKAGE_ZIP:-dist-commercial/SagittaDB-Enterprise-v${VERSION}.zip}"
MANIFEST_OUT="${MANIFEST_OUT:-backend/COMMERCIAL-MANIFEST.json}"
SBOM_DIR="${SBOM_DIR:-dist-commercial/sbom}"
PYTHON_BIN="${PYTHON:-}"
COSIGN_TIMEOUT="${COSIGN_TIMEOUT:-10m}"

# cosign 用于签名已推送镜像的 digest；下面生成的 JSON 签名用于保护
# 会在镜像仓库之外流转的客户部署包。
if ! command -v cosign >/dev/null 2>&1; then
  echo "cosign is required for image signing" >&2
  exit 1
fi
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required for artifact signing" >&2
    exit 1
  fi
fi
cosign_args=(--timeout "${COSIGN_TIMEOUT}")
if [[ -n "${COSIGN_KEY:-}" ]]; then
  cosign_args+=(--key "${COSIGN_KEY}")
fi
if [[ "${COSIGN_USE_SIGNING_CONFIG:-false}" != "true" ]]; then
  cosign_args+=(--use-signing-config=false)
fi

"${PYTHON_BIN}" tools/sign_manifest.py \
  --root backend \
  --version "${VERSION}" \
  --out "${MANIFEST_OUT}" \
  app alembic.ini

cosign sign --yes "${cosign_args[@]}" "${IMAGE_REPOSITORY}-backend:${VERSION}"
cosign sign --yes "${cosign_args[@]}" "${IMAGE_REPOSITORY}-frontend:${VERSION}"

for component in backend frontend; do
  sbom="${SBOM_DIR}/sagittadb-${component}-${VERSION}.cyclonedx.json"
  if [[ ! -s "${sbom}" ]]; then
    echo "Required SBOM is missing or empty: ${sbom}" >&2
    exit 1
  fi
  image="${IMAGE_REPOSITORY}-${component}:${VERSION}"
  cosign sign-blob --yes "${cosign_args[@]}" --bundle "${sbom}.bundle" "${sbom}"
  cosign attest --yes "${cosign_args[@]}" --new-bundle-format=false --type cyclonedx --predicate "${sbom}" "${image}"
done

"${PYTHON_BIN}" - <<'PY' "${PACKAGE_ZIP}"
import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

zip_path = Path(sys.argv[1])
key = os.environ.get("MANIFEST_PRIVATE_KEY") or os.environ.get("LICENSE_PRIVATE_KEY", "")
if not key.strip():
    raise SystemExit("MANIFEST_PRIVATE_KEY is required")
key = key.strip()
if "BEGIN PRIVATE KEY" in key:
    loaded = serialization.load_pem_private_key(key.encode(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise SystemExit("MANIFEST_PRIVATE_KEY is not an Ed25519 private key")
    private_key = loaded
else:
    padded = key + "=" * (-len(key) % 4)
    private_key = Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(padded.encode()))
payload = {
    "product": "sagittadb",
    "artifact": zip_path.name,
    "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
    "issued_at": datetime.now(UTC).isoformat(),
}
canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
signature = base64.urlsafe_b64encode(private_key.sign(canonical)).decode().rstrip("=")
zip_path.with_suffix(zip_path.suffix + ".sig.json").write_text(
    json.dumps({"payload": payload, "signature": signature}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
