from pathlib import Path

import yaml

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
LICENSE_SERVER_URL = "https://license.loveai.asia"
LICENSE_PUBLIC_KEY = "3Jz3SK-mTWZwGy6VX8gUBUWJ-kisvGnO3c_x18Fk_Ms"
LICENSE_TRIAL_DAYS = "60"


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_settings_default_online_license_config():
    settings = Settings(_env_file=None)

    assert settings.LICENSE_PUBLIC_KEY == LICENSE_PUBLIC_KEY
    assert settings.LICENSE_SERVER_URL == LICENSE_SERVER_URL
    assert settings.LICENSE_TRIAL_DAYS == 60


def test_source_and_commercial_env_templates_share_license_defaults():
    for relative_path in (
        ".env.example",
        "deploy/customer/.env.example",
        "dist-commercial/SagittaDB-Enterprise-v2.2.0/.env.example",
    ):
        values = _env_values(REPO_ROOT / relative_path)

        assert values["LICENSE_PUBLIC_KEY"] == LICENSE_PUBLIC_KEY
        assert values["LICENSE_SERVER_URL"] == LICENSE_SERVER_URL
        assert values["LICENSE_TRIAL_DAYS"] == LICENSE_TRIAL_DAYS


def test_helm_values_share_license_defaults():
    for relative_path in (
        "deploy/helm/sagittadb/values.yaml",
        "dist-commercial/SagittaDB-Enterprise-v2.2.0/helm/sagittadb/values.yaml",
    ):
        values = yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))

        assert values["license"]["publicKey"] == LICENSE_PUBLIC_KEY
        assert values["license"]["serverUrl"] == LICENSE_SERVER_URL
        assert values["license"]["trialDays"] == 60
