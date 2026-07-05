#!/usr/bin/env python3
"""渲染并校验 Sagitta Control 客户部署包。"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path


PACKAGE_FILES = {
    "deploy/customer/docker-compose.yml": "docker-compose.yml",
    "deploy/customer/.env.example": ".env.example",
    "deploy/customer/prepare-go-live-env.sh": "prepare-go-live-env.sh",
    "deploy/customer/go-live-check.sh": "go-live-check.sh",
    "deploy/customer/upgrade.sh": "upgrade.sh",
    "deploy/customer/verify-license.sh": "verify-license.sh",
    "deploy/nginx.conf": "nginx.conf",
}
PACKAGE_DOC_FILES = {
    "docs/installation_deployment.md": "docs/installation_deployment.md",
    "docs/user_manual.md": "docs/user_manual.md",
    "docs/operations_upgrade.md": "docs/operations_upgrade.md",
}
PACKAGE_DIRS = {
    "docs/screenshots/user-manual": "screenshots",
    "deploy/helm/sagitta-control": "helm/sagitta-control",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"LICENSE_PRIVATE_KEY"),
    re.compile(r"MANIFEST_PRIVATE_KEY"),
    re.compile(r"LICENSE_SERVER_TOKEN"),
    re.compile(r"private_key\s*=", re.IGNORECASE),
]

BINARY_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"(^|/)backend(/|$)"),
    re.compile(r"(^|/)frontend(/|$)"),
    re.compile(r"(^|/)tools(/|$)"),
    re.compile(r"(^|/)scripts/build-commercial-images\.sh$"),
    re.compile(r"(^|/)scripts/compile-nuitka-core\.sh$"),
    re.compile(r"(^|/)scripts/sign-commercial-artifacts\.sh$"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="渲染客户部署包，并在固定版本、占位符或私钥材料校验失败时退出。",
    )
    parser.add_argument("--version", required=True, help="发布版本，例如 1.0.0")
    parser.add_argument(
        "--image-repository",
        required=True,
        help="镜像仓库前缀，例如 ghcr.io/acme/sagitta-control",
    )
    parser.add_argument(
        "--output-dir",
        default="dist-commercial",
        help="客户包目录和压缩包输出位置。",
    )
    parser.add_argument(
        "--package-name",
        help="可选客户包目录/压缩包名称，默认 Sagitta-Control-v<version>。",
    )
    return parser.parse_args()


def copy_package_files(repo_root: Path, package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    for src, dest in PACKAGE_FILES.items():
        shutil.copy2(repo_root / src, package_dir / dest)
    for src, dest in PACKAGE_DIRS.items():
        shutil.copytree(repo_root / src, package_dir / dest)
    for src, dest in PACKAGE_DOC_FILES.items():
        target = package_dir / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / src, target)

    write_customer_readme(package_dir)

    for script in ("prepare-go-live-env.sh", "go-live-check.sh", "upgrade.sh", "verify-license.sh"):
        path = package_dir / script
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_customer_readme(package_dir: Path) -> None:
    (package_dir / "README.md").write_text(
        """# Sagitta Control 客户部署包

Sagitta Control 是面向企业数据库安全管控场景的统一平台。此部署包包含固定版本 Docker Compose、Helm Chart、上线检查脚本、升级脚本、产品截图和标准文档，不包含后端或前端源码。

![交付与支持](screenshots/23-commercial-support.png)

## 文档入口

- [安装部署手册](docs/installation_deployment.md)：服务器准备、Docker Compose / Helm 部署、授权激活和上线检查。
- [产品使用手册](docs/user_manual.md)：平台初始化、权限模型、SQL 工单、在线查询、观测诊断、归档和审计操作。
- [运维升级手册](docs/operations_upgrade.md)：日常巡检、备份、升级、回滚、日志诊断和安全基线。

## 快速部署

```bash
cp .env.example .env
bash prepare-go-live-env.sh
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
bash go-live-check.sh
```

## 运维脚本

- `prepare-go-live-env.sh`：检查 `.env` 中的 `SECRET_KEY`、`LICENSE_DEPLOYMENT_ID`、数据库密码和授权配置。
- `go-live-check.sh`：检查容器、健康接口、授权状态和上线前关键配置。
- `upgrade.sh`：执行固定版本升级、备份、迁移、重启和健康检查。
- `verify-license.sh`：检查授权配置和许可证状态。

共享部署截图、日志和诊断包前，请先确认没有暴露服务器 IP、`.env`、License 文件、激活码、数据库密码、Token 或未脱敏客户数据。
""",
        encoding="utf-8",
    )


def render_placeholders(package_dir: Path, version: str, image_repository: str) -> None:
    registry, repository = split_image_repository(image_repository)
    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in BINARY_ASSET_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("__SAGITTA_CONTROL_VERSION__", version)
        text = text.replace("__IMAGE_REPOSITORY__", image_repository)
        if path.parent.name == "docs":
            text = text.replace("screenshots/user-manual/", "../screenshots/")
        if path.name == "Chart.yaml":
            text = re.sub(r"^version: .*$", f"version: {version}", text, flags=re.MULTILINE)
            text = re.sub(r"^appVersion: .*$", f'appVersion: "{version}"', text, flags=re.MULTILINE)
        if path.name.startswith("values"):
            text = text.replace("registry: ghcr.io", f"registry: {registry}")
            text = text.replace("repository: your-org/sagitta-control-frontend", f"repository: {repository}-frontend")
            text = text.replace("repository: your-org/sagitta-control", f"repository: {repository}-backend")
            text = re.sub(r'tag: "1\.0\.0"', f'tag: "{version}"', text)
        path.write_text(text, encoding="utf-8")


def split_image_repository(image_repository: str) -> tuple[str, str]:
    parts = image_repository.split("/", 1)
    if len(parts) != 2:
        raise ValueError("--image-repository 必须包含 registry/repository，例如 ghcr.io/acme/sagitta-control")
    return parts[0], parts[1]


def validate_package(package_dir: Path, version: str) -> list[str]:
    errors: list[str] = []
    expected = sorted([Path("README.md"), *(Path(dest) for dest in PACKAGE_FILES.values())])
    actual = sorted(path.relative_to(package_dir) for path in package_dir.iterdir() if path.is_file())
    if actual != expected:
        errors.append(f"客户包文件不匹配：应为 {expected}，实际为 {actual}")

    combined_text = ""
    for path in package_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() not in BINARY_ASSET_SUFFIXES:
            combined_text += f"\n--- {path.name} ---\n"
            combined_text += path.read_text(encoding="utf-8")

    if "__SAGITTA_CONTROL_VERSION__" in combined_text or "__IMAGE_REPOSITORY__" in combined_text:
        errors.append("客户包中仍存在未渲染占位符")

    screenshot_dir = package_dir / "screenshots"
    screenshots = sorted(screenshot_dir.glob("*.png"))
    if len(screenshots) < 10:
        errors.append("客户包截图数量不足，README 和产品手册需要可展示的产品截图")

    readme_path = package_dir / "README.md"
    installation_path = package_dir / "docs" / "installation_deployment.md"
    operations_path = package_dir / "docs" / "operations_upgrade.md"
    if readme_path.exists() and "screenshots/" not in readme_path.read_text(encoding="utf-8"):
        errors.append("README.md 未引用产品截图")
    required_doc_snippets = {
        readme_path: [
            "prepare-go-live-env.sh",
            "go-live-check.sh",
            "upgrade.sh",
            "SECRET_KEY",
            "LICENSE_DEPLOYMENT_ID",
        ],
        installation_path: [
            "sha256sum -c",
            "prepare-go-live-env.sh",
            "docker compose run --rm backend alembic upgrade head",
            "go-live-check.sh",
        ],
        operations_path: [
            "pg_dump",
            "upgrade.sh",
            "gunzip -c",
            "docker compose logs --tail=200 backend",
        ],
    }
    for path, snippets in required_doc_snippets.items():
        if not path.exists():
            errors.append(f"客户包缺少关键文档：{path.relative_to(package_dir)}")
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"{path.relative_to(package_dir)} 缺少关键操作说明：{snippet}")

    for path in [readme_path, *(package_dir / "docs").glob("*.md")]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)|(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
            target = match.group(1) or match.group(2)
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            linked_path = (path.parent / target).resolve()
            try:
                linked_path.relative_to(package_dir.resolve())
            except ValueError:
                errors.append(f"{path.relative_to(package_dir)} 的链接越过客户包目录：{target}")
                continue
            if not linked_path.exists():
                errors.append(f"{path.relative_to(package_dir)} 的链接不存在：{target}")

    if re.search(r":latest\b", combined_text):
        errors.append("客户包禁止引用 :latest 镜像")

    if re.search(r"\bbuild\s*:", combined_text):
        errors.append("客户包禁止包含本地源码 build 配置")

    if "sourceMappingURL" in combined_text:
        errors.append("客户包禁止包含 sourceMappingURL 引用")

    if not re.search(rf"-backend:{re.escape(version)}\b", combined_text):
        errors.append("后端镜像未使用指定固定版本")

    if not re.search(rf"-frontend:{re.escape(version)}\b", combined_text):
        errors.append("前端镜像未使用指定固定版本")

    for pattern in SECRET_PATTERNS:
        if pattern.search(combined_text):
            errors.append(f"客户包疑似包含 License 私钥材料：{pattern.pattern}")

    for path in package_dir.rglob("*"):
        relative = path.relative_to(package_dir).as_posix()
        if path.is_file() and path.suffix in {".py", ".pyc", ".pyo", ".map", ".ts", ".tsx"}:
            errors.append(f"客户包禁止包含源码或 sourcemap 文件：{relative}")
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(relative):
                errors.append(f"客户包禁止包含内部源码/构建路径：{relative}")
                break

    return errors


def make_zip(package_dir: Path, output_dir: Path, package_name: str) -> Path:
    zip_path = output_dir / f"{package_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir))
    return zip_path


def write_sha256(zip_path: Path) -> Path:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    checksum_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output_dir).resolve()
    package_name = args.package_name or f"Sagitta-Control-v{args.version}"
    package_dir = output_dir / package_name

    if package_dir.exists():
        shutil.rmtree(package_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    copy_package_files(repo_root, package_dir)
    render_placeholders(package_dir, args.version, args.image_repository)

    errors = validate_package(package_dir, args.version)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    zip_path = make_zip(package_dir, output_dir, package_name)
    checksum_path = write_sha256(zip_path)

    print(f"客户包目录：{package_dir}")
    print(f"压缩包：{zip_path}")
    print(f"SHA256: {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
