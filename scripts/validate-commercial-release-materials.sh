#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:?VERSION is required, e.g. 2.2.0}"
PACKAGE_NAME="${PACKAGE_NAME:-SagittaDB-Enterprise-v${VERSION}}"
DIST_DIR="${DIST_DIR:-dist-commercial}"
SBOM_DIR="${SBOM_DIR:-${DIST_DIR}/sbom}"

package_zip="${DIST_DIR}/${PACKAGE_NAME}.zip"
package_sha256="${package_zip}.sha256"
package_signature="${package_zip}.sig.json"
python_bin="${PYTHON:-}"

fail() {
  echo "$*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -s "${path}" ]] || fail "Required release material is missing or empty: ${path}"
}

check_sha256_file() {
  local checksum_file="$1"
  local dir
  dir="$(dirname "${checksum_file}")"
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "${dir}" && sha256sum --check "$(basename "${checksum_file}")")
  else
    (cd "${dir}" && shasum -a 256 --check "$(basename "${checksum_file}")")
  fi
}

if [[ -z "${python_bin}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  else
    fail "python3 or python is required to validate release materials"
  fi
fi

require_file "${package_zip}"
require_file "${package_sha256}"
require_file "${package_signature}"
check_sha256_file "${package_sha256}"

"${python_bin}" - <<'PY' "${package_zip}" "${package_signature}"
import hashlib
import json
import sys
from pathlib import Path

zip_path = Path(sys.argv[1])
signature_path = Path(sys.argv[2])
doc = json.loads(signature_path.read_text(encoding="utf-8"))
payload = doc.get("payload")
signature = doc.get("signature")
if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
    raise SystemExit(f"{signature_path} must contain payload and signature")
if payload.get("product") != "sagittadb":
    raise SystemExit(f"{signature_path} product must be sagittadb")
if payload.get("artifact") != zip_path.name:
    raise SystemExit(f"{signature_path} artifact does not match {zip_path.name}")
actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
if payload.get("sha256") != actual:
    raise SystemExit(f"{signature_path} sha256 does not match {zip_path.name}")
PY

for component in backend frontend; do
  sbom="${SBOM_DIR}/sagittadb-${component}-${VERSION}.cyclonedx.json"
  sbom_sha256="${sbom}.sha256"
  sbom_bundle="${sbom}.bundle"
  require_file "${sbom}"
  require_file "${sbom_sha256}"
  require_file "${sbom_bundle}"
  check_sha256_file "${sbom_sha256}"
  "${python_bin}" - <<'PY' "${sbom}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
doc = json.loads(path.read_text(encoding="utf-8"))
if doc.get("bomFormat") != "CycloneDX":
    raise SystemExit(f"{path} is not a CycloneDX SBOM")
PY
done

echo "Commercial release materials validated for ${PACKAGE_NAME}"
