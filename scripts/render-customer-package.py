#!/usr/bin/env python3
"""渲染并校验 SagittaDB Enterprise 客户部署包。"""

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
    "deploy/customer/LEGAL-NOTICE.md": "LEGAL-NOTICE.md",
    "deploy/nginx.conf": "nginx.conf",
}
PACKAGE_DIRS = {
    "deploy/customer/docs": "docs",
    "deploy/helm/sagittadb": "helm/sagittadb",
}

CUSTOMER_README_TEMPLATE = """# SagittaDB Enterprise v__SAGITTADB_VERSION__

SagittaDB Enterprise 是面向企业数据库治理场景的统一管控平台，覆盖数据库实例管理、SQL 工单、在线查询、查询权限、数据字典、数据脱敏、SQL 洞察、运行诊断、数据归档、审计追踪和商业交付验收。

本仓库是 SagittaDB Enterprise 的公开交付仓库。这里提供客户部署文件、安装脚本、Helm Chart、产品手册、运维升级指南和版本下载入口；后端源码、前端源码、商业构建脚本、签名私钥和 License 签发工具不在公开仓库中提供。

## 版本与镜像

- 后端：`__IMAGE_REPOSITORY__-backend:__SAGITTADB_VERSION__`
- 前端：`__IMAGE_REPOSITORY__-frontend:__SAGITTADB_VERSION__`

生产环境请始终使用明确版本标签。首次部署会自动进入 60 天全功能试用期；试用到期后业务功能将暂停，仅保留登录和授权管理入口。在线授权默认需要至少每 7 天成功联网刷新一次；长期离线部署请使用 challenge-response 离线授权。

## 文档

- [安装部署指南](docs/installation.md)
- [运维升级指南](docs/operations-upgrade.md)
- [产品使用手册](docs/product-manual.md)
- [法律提示](LEGAL-NOTICE.md)

## Docker Compose 快速开始

```bash
cp .env.example .env
./prepare-go-live-env.sh --customer-id <customer_id>
# 按现场信息确认 .env 中的授权、域名、端口和通知配置。
docker compose pull
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose ps
```

前端服务健康后，访问 `http://<server>/`。

正式推广前执行上线门禁：

```bash
./go-live-check.sh \\
  --api-base-url http://<server>:8000 \\
  --frontend-url http://<server>/ \\
  --username <admin> \\
  --password '<password>'
```

该脚本要求生产密钥、正式 License、客户 ID、部署指纹、至少一个活跃实例、实施交付向导、验收报告、运行健康和推广就绪度全部通过。若管理员启用了 2FA，请改用 `--token <access_token>`。

## Kubernetes / Helm

仓库内包含 Helm Chart：

```bash
helm dependency update helm/sagittadb
helm upgrade --install sagittadb helm/sagittadb \\
  -f helm/sagittadb/values-prod.yaml \\
  --set app.secretKey='<random-secret>' \\
  --set license.customerId='<customer-id>' \\
  --set license.deploymentId='<stable-deployment-id>'
```

## 下载安装包

可以从本仓库的 GitHub Releases 下载完整部署包：

```bash
wget https://github.com/Lynn-Lee/SagittaDB-Enterprise/releases/download/v__SAGITTADB_VERSION__/SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip
wget https://github.com/Lynn-Lee/SagittaDB-Enterprise/releases/download/v__SAGITTADB_VERSION__/SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256
sha256sum -c SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip.sha256
unzip SagittaDB-Enterprise-v__SAGITTADB_VERSION__.zip
cd SagittaDB-Enterprise-v__SAGITTADB_VERSION__
```

## 升级入口

```bash
./upgrade.sh __SAGITTADB_VERSION__
```

升级脚本会更新镜像版本、拉取镜像、备份 PostgreSQL、执行 Alembic 迁移并检查前后端健康状态。升级前请阅读 [运维升级指南](docs/operations-upgrade.md)。

## 离线镜像导入

如果服务器无法访问镜像仓库，请导入 SagittaDB 支持团队提供的镜像包：

```bash
docker load < sagittadb-backend-__SAGITTADB_VERSION__.tar
docker load < sagittadb-frontend-__SAGITTADB_VERSION__.tar
docker compose up -d
```

## License 与试用

登录后可在授权管理页面输入在线激活码完成授权，或生成离线 Challenge 后导入商务侧返回的 challenge-response 文件。也可以使用 `verify-license.sh` 验证在线激活、离线 Challenge 生成和刷新流程：

```bash
./verify-license.sh <activation_code> <customer_id>
```

SagittaDB Enterprise 使用统一授权中心 License-Server-Center，客户包默认授权服务地址为 `https://license.loveai.asia`。在线激活和联网刷新会由后端自动提交授权项目码 `sagittadb`，授权管理页应显示 `授权项目：SagittaDB（sagittadb）`。

在线激活前，在授权管理页输入客户 ID，页面会生成“正式激活客户 ID”和“正式激活部署指纹”。请将该正式激活部署指纹录入用户授权中心，再生成并交付激活码。复制指纹时，HTTPS 环境优先使用浏览器剪贴板能力；HTTP 试用部署会自动使用兼容复制方式。

生产环境默认不接受未绑定 Challenge 的裸 License JSON。
在线激活授权默认 `LICENSE_ONLINE_GRACE_DAYS=7`，超过宽限期未成功回源刷新时业务功能会暂停，直到授权刷新成功。

试用期结束或需要正式生产授权时，请联系 SagittaDB 商业支持，并提供授权管理页展示的正式激活部署指纹。

共享日志或配置时，不要打包 License 文件、私钥、激活码或 `.env` 中的敏感值。

## 安全边界

公开仓库和部署包不包含 SagittaDB 源码、签发工具、私钥、真实客户 License、真实激活码、客户数据库连接信息或内部验收记录。Release 同时提供客户包签名文件、前后端镜像 CycloneDX SBOM 及其校验/签名材料，便于客户侧供应链验收。
"""

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"LICENSE_PRIVATE_KEY"),
    re.compile(r"MANIFEST_PRIVATE_KEY"),
    re.compile(r"LICENSE_SERVER_TOKEN"),
    re.compile(r"private_key\s*=", re.IGNORECASE),
]

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
    for src, dest in PACKAGE_DIRS.items():
        shutil.copytree(repo_root / src, package_dir / dest)
    (package_dir / "README.md").write_text(CUSTOMER_README_TEMPLATE, encoding="utf-8")

    for script in ("prepare-go-live-env.sh", "go-live-check.sh", "upgrade.sh", "verify-license.sh"):
        path = package_dir / script
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_placeholders(package_dir: Path, version: str, image_repository: str) -> None:
    registry, repository = split_image_repository(image_repository)
    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace("__SAGITTADB_VERSION__", version)
        text = text.replace("__IMAGE_REPOSITORY__", image_repository)
        if path.name == "Chart.yaml":
            text = re.sub(r"^version: .*$", f"version: {version}", text, flags=re.MULTILINE)
            text = re.sub(r"^appVersion: .*$", f'appVersion: "{version}"', text, flags=re.MULTILINE)
        if path.name.startswith("values"):
            text = text.replace("registry: ghcr.io", f"registry: {registry}")
            text = text.replace("repository: your-org/sagittadb-frontend", f"repository: {repository}-frontend")
            text = text.replace("repository: your-org/sagittadb", f"repository: {repository}-backend")
            text = re.sub(r'tag: "1\.0\.0"', f'tag: "{version}"', text)
        path.write_text(text, encoding="utf-8")


def split_image_repository(image_repository: str) -> tuple[str, str]:
    parts = image_repository.split("/", 1)
    if len(parts) != 2:
        raise ValueError("--image-repository 必须包含 registry/repository，例如 ghcr.io/acme/sagittadb")
    return parts[0], parts[1]


def validate_package(package_dir: Path, version: str) -> list[str]:
    errors: list[str] = []
    expected = sorted([Path(dest) for dest in PACKAGE_FILES.values()] + [Path("README.md")])
    actual = sorted(path.relative_to(package_dir) for path in package_dir.iterdir() if path.is_file())
    if actual != expected:
        errors.append(f"客户包文件不匹配：应为 {expected}，实际为 {actual}")

    combined_text = ""
    for path in package_dir.rglob("*"):
        if path.is_file():
            combined_text += f"\n--- {path.name} ---\n"
            combined_text += path.read_text(encoding="utf-8")

    if "__SAGITTADB_VERSION__" in combined_text or "__IMAGE_REPOSITORY__" in combined_text:
        errors.append("客户包中仍存在未渲染占位符")

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
