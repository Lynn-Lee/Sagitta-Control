#!/usr/bin/env python3
"""生成并签名商业镜像完整性 Manifest。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_private_key() -> Ed25519PrivateKey:
    value = os.environ.get("MANIFEST_PRIVATE_KEY") or os.environ.get("LICENSE_PRIVATE_KEY", "")
    value = value.strip()
    if not value:
        raise SystemExit("MANIFEST_PRIVATE_KEY is required")
    if "BEGIN PRIVATE KEY" in value:
        loaded = serialization.load_pem_private_key(value.encode(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise SystemExit("MANIFEST_PRIVATE_KEY is not an Ed25519 private key")
        return loaded
    padded = value + "=" * (-len(value) % 4)
    return Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(padded.encode()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="签名 SagittaDB 商业镜像完整性 Manifest")
    parser.add_argument("--root", default="backend", help="Manifest root directory")
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("paths", nargs="+", help="Files or directories relative to --root")
    return parser.parse_args()


def iter_files(root: Path, paths: list[str]) -> list[Path]:
    result: list[Path] = []
    for item in paths:
        path = (root / item).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"path outside root: {item}") from exc
        if path.is_dir():
            result.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        elif path.is_file():
            result.append(path)
        else:
            raise SystemExit(f"path not found: {item}")
    return sorted(set(result))


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    files = [
        {
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in iter_files(root, args.paths)
    ]
    payload = {
        "product": "sagittadb",
        "version": args.version,
        "algorithm": "sha256",
        "issued_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    private_key = load_private_key()
    document = {
        "payload": payload,
        "signature": b64url(private_key.sign(canonical_payload(payload))),
    }
    Path(args.out).write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
