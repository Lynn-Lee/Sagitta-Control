#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 1.0.5}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required, e.g. ghcr.io/acme/sagittadb}"
PACKAGE_ZIP="${PACKAGE_ZIP:-dist-commercial/SagittaDB-Enterprise-v${VERSION}.zip}"
MANIFEST_OUT="${MANIFEST_OUT:-backend/COMMERCIAL-MANIFEST.json}"

# cosign signs the pushed image digests; the JSON signature below covers the
# customer deployment package that travels outside the registry.
if ! command -v cosign >/dev/null 2>&1; then
  echo "cosign is required for image signing" >&2
  exit 1
fi

python tools/sign_manifest.py \
  --root backend \
  --version "${VERSION}" \
  --out "${MANIFEST_OUT}" \
  app

cosign sign --yes "${IMAGE_REPOSITORY}-backend:${VERSION}"
cosign sign --yes "${IMAGE_REPOSITORY}-frontend:${VERSION}"

python - <<'PY' "${PACKAGE_ZIP}"
import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

zip_path = Path(sys.argv[1])
key = os.environ.get("MANIFEST_PRIVATE_KEY") or os.environ.get("LICENSE_PRIVATE_KEY", "")
if not key.strip():
    raise SystemExit("MANIFEST_PRIVATE_KEY is required")
padded = key.strip() + "=" * (-len(key.strip()) % 4)
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
