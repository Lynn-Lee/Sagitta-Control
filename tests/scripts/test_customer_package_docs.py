from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_render_script():
    spec = importlib.util.spec_from_file_location(
        "render_customer_package_test",
        ROOT / "scripts" / "render-customer-package.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_customer_package_test"] = module
    spec.loader.exec_module(module)
    return module


def test_customer_readme_does_not_render_explanatory_blockquotes(tmp_path):
    render_customer_package = load_render_script()

    render_customer_package.write_customer_readme(tmp_path)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "\n> " not in readme
    assert "版本：" not in readme
    assert "镜像仓库：" not in readme
    assert "screenshots/23-commercial-support.png" in readme


def test_public_release_validation_uses_current_customer_doc_paths():
    workflow = (ROOT / ".github" / "workflows" / "commercial-release.yml").read_text(encoding="utf-8")

    for path in (
        "docs/installation_deployment.md",
        "docs/user_manual.md",
        "docs/operations_upgrade.md",
    ):
        assert path in workflow

    for stale_path in (
        "docs/installation.md",
        "docs/product-manual.md",
        "docs/operations-upgrade.md",
        "docs/release_templates/sagitta_control_public_release.md",
    ):
        assert stale_path not in workflow
    assert "../screenshots/23-commercial-support.png" in workflow
    assert "../screenshots/02-dashboard-query.png" not in workflow
