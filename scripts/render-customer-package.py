#!/usr/bin/env python3
"""渲染并校验 SagittaDB Enterprise 客户部署包。"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path


PACKAGE_FILES = {
    "deploy/customer/docker-compose.yml": "docker-compose.yml",
    "deploy/customer/.env.example": ".env.example",
    "deploy/customer/upgrade.sh": "upgrade.sh",
    "deploy/customer/verify-license.sh": "verify-license.sh",
    "deploy/nginx.conf": "nginx.conf",
}

CUSTOMER_README_TEMPLATE = """# SagittaDB Enterprise v__SAGITTADB_VERSION__

这是 SagittaDB Enterprise 客户部署包。部署包只包含生产部署配置，应用代码通过固定版本 Docker 镜像交付。

## 镜像

- 后端：`__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- 前端：`__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`

生产环境不要使用 `latest`，请保留 `docker-compose.yml` 中的明确版本标签。

## 首次部署

```bash
cp .env.example .env
# 编辑 .env，替换所有 CHANGE_ME 值。
docker login ghcr.io
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

前端服务健康后，访问 `http://<server>/`。

## 升级

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

升级脚本会更新镜像标签、拉取镜像、备份 PostgreSQL、执行 Alembic 迁移并检查前后端健康状态。

## 离线镜像导入

如果服务器无法访问镜像仓库，请导入 SagittaDB 支持团队提供的镜像包：

```bash
docker load < sagittadb-backend-__SAGITTADB_VERSION__.tar
docker load < sagittadb-frontend-__SAGITTADB_VERSION__.tar
docker compose up -d
```

## License

登录后可在授权管理页面导入离线 License，或输入在线激活码完成授权。也可以使用 `verify-license.sh` 验证在线激活和刷新流程：

```bash
./verify-license.sh <activation_code> <customer_id>
```

共享日志或配置时，不要打包 License 文件、私钥、激活码或 `.env` 中的敏感值。
"""

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"SAGITTADB_LICENSE_PRIVATE_KEY"),
    re.compile(r"LICENSE_PRIVATE_KEY"),
    re.compile(r"private_key\s*=", re.IGNORECASE),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="渲染客户部署包，并在固定版本、占位符或私钥材料校验失败时退出。",
    )
    parser.add_argument("--version", required=True, help="发布版本，例如 1.0.0")
    parser.add_argument(
        "--image-repository",
        required=True,
        help="镜像仓库前缀，例如 ghcr.io/acme/sagittadb",
    )
    parser.add_argument(
        "--output-dir",
        default="dist-commercial",
        help="客户包目录和压缩包输出位置。",
    )
    parser.add_argument(
        "--package-name",
        help="可选客户包目录/压缩包名称，默认 SagittaDB-Enterprise-v<version>。",
    )
    return parser.parse_args()


def copy_package_files(repo_root: Path, package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    for src, dest in PACKAGE_FILES.items():
        shutil.copy2(repo_root / src, package_dir / dest)
    (package_dir / "README.md").write_text(CUSTOMER_README_TEMPLATE, encoding="utf-8")

    for script in ("upgrade.sh", "verify-license.sh"):
        path = package_dir / script
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_placeholders(package_dir: Path, version: str, image_repository: str) -> None:
    for path in package_dir.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("__SAGITTADB_VERSION__", version)
        text = text.replace("__IMAGE_REPOSITORY__", image_repository)
        path.write_text(text, encoding="utf-8")


def validate_package(package_dir: Path, version: str) -> list[str]:
    errors: list[str] = []
    expected = sorted([Path(dest) for dest in PACKAGE_FILES.values()] + [Path("README.md")])
    actual = sorted(path.relative_to(package_dir) for path in package_dir.iterdir() if path.is_file())
    if actual != expected:
        errors.append(f"客户包文件不匹配：应为 {expected}，实际为 {actual}")

    combined_text = ""
    for path in package_dir.iterdir():
        if path.is_file():
            combined_text += f"\n--- {path.name} ---\n"
            combined_text += path.read_text(encoding="utf-8")

    if "__SAGITTADB_VERSION__" in combined_text or "__IMAGE_REPOSITORY__" in combined_text:
        errors.append("客户包中仍存在未渲染占位符")

    if re.search(r":latest\b", combined_text):
        errors.append("客户包禁止引用 :latest 镜像")

    if not re.search(rf"-backend:{re.escape(version)}\b", combined_text):
        errors.append("后端镜像未使用指定固定版本")

    if not re.search(rf"-frontend:{re.escape(version)}\b", combined_text):
        errors.append("前端镜像未使用指定固定版本")

    for pattern in SECRET_PATTERNS:
        if pattern.search(combined_text):
            errors.append(f"客户包疑似包含 License 私钥材料：{pattern.pattern}")

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
    package_name = args.package_name or f"SagittaDB-Enterprise-v{args.version}"
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
