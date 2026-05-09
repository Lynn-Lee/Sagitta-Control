#!/usr/bin/env python3
"""签发 SagittaDB Enterprise License 文件。

私钥必须通过 LICENSE_PRIVATE_KEY 提供，禁止提交到仓库或复制到客户镜像。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_FEATURES = ["workflow", "query", "archive", "monitor", "ai", "masking", "instance"]
LICENSE_PROJECT_CODE = "sagittadb"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_private_key() -> Ed25519PrivateKey:
    value = os.environ.get("LICENSE_PRIVATE_KEY", "").strip()
    if not value:
        raise SystemExit("LICENSE_PRIVATE_KEY is required")
    if "BEGIN PRIVATE KEY" in value:
        loaded = serialization.load_pem_private_key(value.encode(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise SystemExit("LICENSE_PRIVATE_KEY is not an Ed25519 private key")
        return loaded
    padded = value + "=" * (-len(value) % 4)
    return Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(padded.encode()))


def generate_keypair() -> None:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    print("LICENSE_PRIVATE_KEY=" + b64url(private_raw))
    print("LICENSE_PUBLIC_KEY=" + b64url(public_raw))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="签发 SagittaDB Enterprise License")
    parser.add_argument("--generate-keypair", action="store_true", help="生成一组新的 Ed25519 密钥后退出")
    parser.add_argument("--license-id", required=False, help="License 标识")
    parser.add_argument("--customer-id", required=False, help="客户标识")
    parser.add_argument("--company-name", required=False, help="客户公司名称")
    parser.add_argument("--edition", default="enterprise", help="版本名称")
    parser.add_argument("--days", type=int, default=365, help="从现在起的有效天数")
    parser.add_argument("--not-before", default="", help="ISO 时间；默认当前时间")
    parser.add_argument("--expires-at", default="", help="ISO 时间；优先于 --days")
    parser.add_argument("--features", default=",".join(DEFAULT_FEATURES), help="逗号分隔的功能列表")
    parser.add_argument("--max-instances", type=int, default=0, help="0 表示不限制")
    parser.add_argument("--max-users", type=int, default=0, help="0 表示不限制")
    parser.add_argument("--deployment-fingerprint", default="", help="将 License 绑定到单个 SagittaDB 部署")
    parser.add_argument("--challenge-file", default="", help="离线 Challenge JSON；自动填充 customer_id 和 deployment_fingerprint")
    parser.add_argument("--response-out", default="", help="输出 challenge-response JSON 路径；为空则只输出 License")
    parser.add_argument("--out", default="", help="输出路径；为空时输出到 stdout")
    return parser.parse_args()


def parse_dt(value: str) -> datetime:
    if not value:
        return datetime.now(UTC)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def main() -> int:
    args = parse_args()
    if args.generate_keypair:
        generate_keypair()
        return 0

    challenge_doc: dict[str, Any] | None = None
    if args.challenge_file:
        challenge_doc = json.loads(Path(args.challenge_file).read_text(encoding="utf-8"))
        challenge_payload = challenge_doc.get("payload") if isinstance(challenge_doc, dict) else None
        if not isinstance(challenge_payload, dict):
            raise SystemExit("challenge file must contain payload")
        if not args.customer_id:
            args.customer_id = str(challenge_payload.get("customer_id") or "")
        if not args.deployment_fingerprint:
            args.deployment_fingerprint = str(challenge_payload.get("deployment_fingerprint") or "")

    missing = [
        name
        for name in ("license_id", "customer_id", "company_name")
        if not getattr(args, name)
    ]
    if missing:
        raise SystemExit("Missing required arguments: " + ", ".join("--" + m.replace("_", "-") for m in missing))

    private_key = load_private_key()
    not_before = parse_dt(args.not_before)
    expires_at = parse_dt(args.expires_at) if args.expires_at else not_before + timedelta(days=args.days)
    features = [item.strip() for item in args.features.split(",") if item.strip()]
    limits: dict[str, int] = {}
    if args.max_instances:
        limits["max_instances"] = args.max_instances
    if args.max_users:
        limits["max_users"] = args.max_users

    payload = {
        "license_id": args.license_id,
        "project": LICENSE_PROJECT_CODE,
        "product": LICENSE_PROJECT_CODE,
        "customer_id": args.customer_id,
        "company_name": args.company_name,
        "edition": args.edition,
        "issued_at": datetime.now(UTC).isoformat(),
        "not_before": not_before.isoformat(),
        "expires_at": expires_at.isoformat(),
        "features": features,
        "limits": limits,
    }
    if args.deployment_fingerprint:
        payload["deployment_fingerprint"] = args.deployment_fingerprint
    signature = b64url(private_key.sign(canonical_payload(payload)))
    document = {"payload": payload, "signature": signature}
    if challenge_doc:
        response_doc = {"challenge": challenge_doc, "license": document}
        response_output = json.dumps(response_doc, ensure_ascii=False, indent=2, sort_keys=True)
        if args.response_out:
            Path(args.response_out).write_text(response_output + "\n", encoding="utf-8")
    output = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
