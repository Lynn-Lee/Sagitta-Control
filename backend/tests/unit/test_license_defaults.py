import subprocess
import sys
from pathlib import Path

import yaml

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_VERSION = "2.2.2"
IMAGE_REPOSITORY = "ghcr.io/lynn-lee/sagitta-control"
LICENSE_SERVER_URL = "https://license.loveai.asia"
LICENSE_PUBLIC_KEY = "3Jz3SK-mTWZwGy6VX8gUBUWJ-kisvGnO3c_x18Fk_Ms"


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


def _render_customer_package(tmp_path: Path) -> Path:
    output_dir = tmp_path / "dist-commercial"
    package_name = f"Sagitta-Control-v{PRODUCT_VERSION}"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/render-customer-package.py"),
            "--version",
            PRODUCT_VERSION,
            "--image-repository",
            IMAGE_REPOSITORY,
            "--output-dir",
            str(output_dir),
            "--package-name",
            package_name,
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    return output_dir / package_name


def test_source_and_commercial_env_templates_share_license_defaults(tmp_path):
    package_dir = _render_customer_package(tmp_path)
    for relative_path in (
        ".env.example",
        "deploy/customer/.env.example",
    ):
        values = _env_values(REPO_ROOT / relative_path)

        assert values["LICENSE_PUBLIC_KEY"] == LICENSE_PUBLIC_KEY
        assert values["LICENSE_SERVER_URL"] == LICENSE_SERVER_URL

    values = _env_values(package_dir / ".env.example")
    assert values["LICENSE_PUBLIC_KEY"] == LICENSE_PUBLIC_KEY
    assert values["LICENSE_SERVER_URL"] == LICENSE_SERVER_URL


def test_helm_values_share_license_defaults(tmp_path):
    package_dir = _render_customer_package(tmp_path)
    for relative_path in (
        "deploy/helm/sagitta-control/values.yaml",
    ):
        values = yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))

        assert values["license"]["publicKey"] == LICENSE_PUBLIC_KEY
        assert values["license"]["serverUrl"] == LICENSE_SERVER_URL

    values = yaml.safe_load((package_dir / "helm/sagitta-control/values.yaml").read_text(encoding="utf-8"))
    assert values["license"]["publicKey"] == LICENSE_PUBLIC_KEY
    assert values["license"]["serverUrl"] == LICENSE_SERVER_URL
