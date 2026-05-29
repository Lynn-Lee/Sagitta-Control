import json

import pytest

from app.core.config import settings
from app.core.integrity import IntegrityError, verify_startup_integrity


def test_integrity_skips_existing_manifest_when_not_required(tmp_path, monkeypatch):
    manifest_path = tmp_path / "COMMERCIAL-MANIFEST.json"
    manifest_path.write_text(json.dumps({"payload": {}, "signature": "invalid"}), encoding="utf-8")

    monkeypatch.setattr(settings, "APP_INTEGRITY_REQUIRED", False)
    monkeypatch.setattr(settings, "SAGITTADB_COMMERCIAL_BUILD", False)
    monkeypatch.setattr(settings, "APP_INTEGRITY_MANIFEST", str(manifest_path))
    monkeypatch.setattr(settings, "MANIFEST_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "LICENSE_PUBLIC_KEY", "")

    verify_startup_integrity()


def test_integrity_requires_manifest_for_commercial_build(tmp_path, monkeypatch):
    manifest_path = tmp_path / "missing-manifest.json"

    monkeypatch.setattr(settings, "APP_INTEGRITY_REQUIRED", False)
    monkeypatch.setattr(settings, "SAGITTADB_COMMERCIAL_BUILD", True)
    monkeypatch.setattr(settings, "APP_INTEGRITY_MANIFEST", str(manifest_path))

    with pytest.raises(IntegrityError, match="完整性 Manifest 不存在"):
        verify_startup_integrity()
