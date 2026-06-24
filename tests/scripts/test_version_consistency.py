from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

VERSION_COPY_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "sagitta_control_prd.md",
    ROOT / "docs" / "operations_guide.md",
    ROOT / "docs" / "user_manual.md",
]
LOGIN_PAGE = ROOT / "frontend" / "src" / "pages" / "auth" / "LoginPage.tsx"


def frontend_version() -> str:
    return json.loads((ROOT / "frontend" / "package.json").read_text())["version"]


def test_outward_facing_version_copy_matches_frontend_package_version():
    version = frontend_version()
    stale_version_pattern = re.compile(r"\bv2\.2\b|\b2\.2\.2\b|v2\.2 商业部署版")
    failures: list[str] = []

    for path in VERSION_COPY_FILES:
        text = path.read_text()
        stale_match = stale_version_pattern.search(text)
        if stale_match:
            failures.append(f"{path.relative_to(ROOT)} still contains {stale_match.group(0)!r}")
        if version not in text:
            failures.append(f"{path.relative_to(ROOT)} does not mention current version {version!r}")

    login_page_text = LOGIN_PAGE.read_text()
    stale_match = stale_version_pattern.search(login_page_text)
    if stale_match:
        failures.append(f"{LOGIN_PAGE.relative_to(ROOT)} still contains {stale_match.group(0)!r}")
    if "APP_VERSION" not in login_page_text:
        failures.append(f"{LOGIN_PAGE.relative_to(ROOT)} should render APP_VERSION instead of a hard-coded version")

    assert not failures, "\n".join(failures)
