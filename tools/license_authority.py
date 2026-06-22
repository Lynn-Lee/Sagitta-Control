#!/usr/bin/env python3
"""用于内部商业运营的轻量 Sagitta Control 授权中心兼容工具。

该工具只适合私有内部环境。它用一个小型 JSON 文件保存激活码和已签发 License，
使用 LICENSE_PRIVATE_KEY 签名，并提供与 Sagitta Control 在线授权客户端兼容的激活和刷新接口。
正式商业运营以统一授权中心 License-Server-Center 为准。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_FEATURES = ["workflow", "query", "archive", "monitor", "ai", "masking", "instance"]
DEFAULT_DB = "license_authority.json"
LICENSE_PROJECT_CODE = "sagitta-control"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def parse_dt(value: str) -> datetime:
    if not value:
        return datetime.now(UTC)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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


def default_store() -> dict[str, Any]:
    return {"activations": {}, "licenses": {}, "audit": []}


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_store()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("activations", {})
    data.setdefault("licenses", {})
    data.setdefault("audit", [])
    return data


def save_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_audit(store: dict[str, Any], action: str, subject: str, detail: dict[str, Any]) -> None:
    store.setdefault("audit", []).append(
        {
            "id": len(store.get("audit", [])) + 1,
            "action": action,
            "subject": subject,
            "detail": detail,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )


def public_activation(code: str, activation: dict[str, Any]) -> dict[str, Any]:
    return {
        "activation_code": code,
        "activation_id": activation.get("activation_id", ""),
        "license_id": activation.get("license_id", ""),
        "customer_id": activation.get("customer_id", ""),
        "company_name": activation.get("company_name", ""),
        "edition": activation.get("edition", "enterprise"),
        "status": activation.get("status", "active"),
        "features": activation.get("features") or DEFAULT_FEATURES,
        "limits": activation.get("limits") or {},
        "deployment_fingerprint": activation.get("deployment_fingerprint", ""),
        "not_before": activation.get("not_before", ""),
        "expires_at": activation.get("expires_at", ""),
        "last_issued_at": activation.get("last_issued_at", ""),
        "updated_at": activation.get("updated_at", ""),
    }


def sign_license(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    return {
        "payload": payload,
        "signature": b64url(private_key.sign(canonical_payload(payload))),
    }


def build_payload(activation: dict[str, Any], license_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    not_before = parse_dt(activation.get("not_before", "")) if activation.get("not_before") else now
    expires_at = parse_dt(activation["expires_at"])
    payload = {
        "license_id": license_id,
        "project": LICENSE_PROJECT_CODE,
        "product": LICENSE_PROJECT_CODE,
        "customer_id": activation["customer_id"],
        "company_name": activation["company_name"],
        "edition": activation.get("edition", "enterprise"),
        "issued_at": now.isoformat(),
        "not_before": not_before.isoformat(),
        "expires_at": expires_at.isoformat(),
        "features": activation.get("features") or DEFAULT_FEATURES,
        "limits": activation.get("limits") or {},
    }
    if activation.get("deployment_fingerprint"):
        payload["deployment_fingerprint"] = activation["deployment_fingerprint"]
    return payload


def create_app(db_path: Path) -> Any:
    try:
        from fastapi import FastAPI, Header, HTTPException
        from pydantic import BaseModel
    except ModuleNotFoundError as exc:
        raise SystemExit("serve requires fastapi and pydantic; run from the backend environment") from exc

    class ActivateRequest(BaseModel):
        activation_code: str
        customer_id: str
        deployment_fingerprint: str = ""
        project: str = LICENSE_PROJECT_CODE
        product: str = LICENSE_PROJECT_CODE

    class RefreshRequest(BaseModel):
        activation_id: str = ""
        license_id: str = ""
        customer_id: str
        deployment_fingerprint: str = ""
        project: str = LICENSE_PROJECT_CODE
        product: str = LICENSE_PROJECT_CODE

    class StatusRequest(BaseModel):
        activation_code: str
        status: str

    class RenewRequest(BaseModel):
        activation_code: str
        days: int | None = None
        expires_at: str = ""
        features: list[str] | None = None
        limits: dict[str, int] | None = None

    app = FastAPI(title="Sagitta Control License-Server-Center Compatibility Authority", version="0.1.0")

    def verify_token(authorization: str | None) -> None:
        expected = os.environ.get("SAGITTA_CONTROL_LICENSE_AUTHORITY_TOKEN", "").strip()
        if not expected:
            return
        if authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="invalid authority token")

    def verify_project(project: str, product: str) -> None:
        requested = (project or product or "").strip().lower()
        if requested and requested != LICENSE_PROJECT_CODE:
            raise HTTPException(status_code=403, detail="授权项目不匹配")

    def issue_for_activation(store: dict[str, Any], code: str, activation: dict[str, Any]) -> dict[str, Any]:
        private_key = load_private_key()
        activation_id = activation.get("activation_id") or f"act-{uuid.uuid4().hex[:12]}"
        license_id = activation.get("license_id") or f"lic-{activation['customer_id']}-{uuid.uuid4().hex[:8]}"
        payload = build_payload(activation, license_id)
        document = sign_license(payload, private_key)
        now = datetime.now(UTC).isoformat()
        activation.update(
            {
                "activation_id": activation_id,
                "license_id": license_id,
                "last_issued_at": now,
                "updated_at": now,
            }
        )
        store["activations"][code] = activation
        store["licenses"][license_id] = {
            "activation_code": code,
            "activation_id": activation_id,
            "customer_id": activation["customer_id"],
            "status": activation.get("status", "active"),
            "license": document,
            "updated_at": now,
        }
        append_audit(
            store,
            "issue_license",
            code,
            {
                "customer_id": activation["customer_id"],
                "license_id": license_id,
                "activation_id": activation_id,
            },
        )
        save_store(db_path, store)
        return {
            "status": activation.get("status", "active"),
            "activation_id": activation_id,
            "license_id": license_id,
            "license": document,
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/licenses/activate")
    async def activate(data: ActivateRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        verify_project(data.project, data.product)
        store = load_store(db_path)
        activation = store["activations"].get(data.activation_code)
        if not activation:
            raise HTTPException(status_code=404, detail="激活码不存在")
        if activation.get("customer_id") != data.customer_id:
            raise HTTPException(status_code=403, detail="客户标识不匹配")
        if activation.get("status", "active") != "active":
            raise HTTPException(status_code=403, detail=f"激活码状态不可用：{activation.get('status')}")
        existing_fingerprint = activation.get("deployment_fingerprint", "")
        if existing_fingerprint and data.deployment_fingerprint and existing_fingerprint != data.deployment_fingerprint:
            append_audit(store, "activate_rejected", data.activation_code, {"reason": "deployment_fingerprint_mismatch"})
            save_store(db_path, store)
            raise HTTPException(status_code=403, detail="部署指纹不匹配")
        if data.deployment_fingerprint and not existing_fingerprint:
            activation["deployment_fingerprint"] = data.deployment_fingerprint
        append_audit(
            store,
            "activate",
            data.activation_code,
            {"customer_id": data.customer_id, "deployment_fingerprint": activation.get("deployment_fingerprint", "")},
        )
        return issue_for_activation(store, data.activation_code, activation)

    @app.post("/api/v1/licenses/refresh")
    async def refresh(data: RefreshRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        verify_project(data.project, data.product)
        store = load_store(db_path)
        license_record = store["licenses"].get(data.license_id)
        if license_record:
            code = license_record["activation_code"]
            activation = store["activations"].get(code)
        else:
            activation = next(
                (
                    item
                    for item in store["activations"].values()
                    if item.get("activation_id") == data.activation_id
                ),
                None,
            )
            code = activation.get("activation_code", "") if activation else ""
        if not activation:
            raise HTTPException(status_code=404, detail="授权记录不存在")
        if activation.get("customer_id") != data.customer_id:
            raise HTTPException(status_code=403, detail="客户标识不匹配")
        existing_fingerprint = activation.get("deployment_fingerprint", "")
        if existing_fingerprint and data.deployment_fingerprint and existing_fingerprint != data.deployment_fingerprint:
            append_audit(store, "refresh_blocked", code or data.activation_id, {"reason": "deployment_fingerprint_mismatch"})
            save_store(db_path, store)
            raise HTTPException(status_code=403, detail="部署指纹不匹配")
        status = activation.get("status", "active")
        if status in {"revoked", "suspended"}:
            append_audit(store, "refresh_blocked", code or data.activation_id, {"status": status})
            save_store(db_path, store)
            return {"status": status, "activation_id": activation.get("activation_id", data.activation_id)}
        append_audit(store, "refresh", code or activation["activation_code"], {"customer_id": data.customer_id})
        return issue_for_activation(store, code or activation["activation_code"], activation)

    @app.get("/api/v1/licenses/activations")
    async def list_activations(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        store = load_store(db_path)
        items = [
            public_activation(code, activation)
            for code, activation in sorted(store["activations"].items())
        ]
        return {"items": items, "total": len(items)}

    @app.get("/api/v1/licenses/audit")
    async def list_audit(limit: int = 100, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        store = load_store(db_path)
        items = list(reversed(store.get("audit", [])))[0:limit]
        return {"items": items, "total": len(store.get("audit", []))}

    @app.post("/api/v1/licenses/status")
    async def set_status(data: StatusRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        if data.status not in {"active", "suspended", "revoked"}:
            raise HTTPException(status_code=400, detail="状态必须是 active/suspended/revoked")
        store = load_store(db_path)
        activation = store["activations"].get(data.activation_code)
        if not activation:
            raise HTTPException(status_code=404, detail="激活码不存在")
        activation["status"] = data.status
        activation["updated_at"] = datetime.now(UTC).isoformat()
        license_id = activation.get("license_id")
        if license_id and license_id in store["licenses"]:
            store["licenses"][license_id]["status"] = data.status
            store["licenses"][license_id]["updated_at"] = activation["updated_at"]
        append_audit(store, "set_status", data.activation_code, {"status": data.status})
        save_store(db_path, store)
        return public_activation(data.activation_code, activation)

    @app.post("/api/v1/licenses/renew")
    async def renew(data: RenewRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        verify_token(authorization)
        store = load_store(db_path)
        activation = store["activations"].get(data.activation_code)
        if not activation:
            raise HTTPException(status_code=404, detail="激活码不存在")
        if data.expires_at:
            activation["expires_at"] = parse_dt(data.expires_at).isoformat()
        elif data.days:
            activation["expires_at"] = (datetime.now(UTC) + timedelta(days=data.days)).isoformat()
        if data.features is not None:
            activation["features"] = data.features
        if data.limits is not None:
            activation["limits"] = data.limits
        activation["updated_at"] = datetime.now(UTC).isoformat()
        append_audit(
            store,
            "renew",
            data.activation_code,
            {
                "expires_at": activation["expires_at"],
                "features": activation.get("features") or DEFAULT_FEATURES,
                "limits": activation.get("limits") or {},
            },
        )
        save_store(db_path, store)
        return issue_for_activation(store, data.activation_code, activation)

    return app


def parse_features(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_limits(args: argparse.Namespace) -> dict[str, int]:
    limits: dict[str, int] = {}
    if args.max_instances:
        limits["max_instances"] = args.max_instances
    if args.max_users:
        limits["max_users"] = args.max_users
    return limits


def command_create_activation(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    store = load_store(db_path)
    now = datetime.now(UTC)
    expires_at = parse_dt(args.expires_at) if args.expires_at else now + timedelta(days=args.days)
    code = args.activation_code or "SGT-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]
    store["activations"][code] = {
        "activation_code": code,
        "customer_id": args.customer_id,
        "company_name": args.company_name,
        "edition": args.edition,
        "status": "active",
        "features": parse_features(args.features),
        "limits": parse_limits(args),
        "deployment_fingerprint": args.deployment_fingerprint,
        "not_before": parse_dt(args.not_before).isoformat() if args.not_before else "",
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    append_audit(store, "create_activation", code, public_activation(code, store["activations"][code]))
    save_store(db_path, store)
    print(code)
    return 0


def command_set_status(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    store = load_store(db_path)
    activation = store["activations"].get(args.activation_code)
    if not activation:
        raise SystemExit("activation code not found")
    activation["status"] = args.status
    activation["updated_at"] = datetime.now(UTC).isoformat()
    license_id = activation.get("license_id")
    if license_id and license_id in store["licenses"]:
        store["licenses"][license_id]["status"] = args.status
        store["licenses"][license_id]["updated_at"] = activation["updated_at"]
    append_audit(store, "set_status", args.activation_code, {"status": args.status})
    save_store(db_path, store)
    return 0


def command_list(args: argparse.Namespace) -> int:
    store = load_store(Path(args.db))
    items = [
        public_activation(code, activation)
        for code, activation in sorted(store["activations"].items())
    ]
    print(json.dumps({"items": items, "total": len(items)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_renew(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    store = load_store(db_path)
    activation = store["activations"].get(args.activation_code)
    if not activation:
        raise SystemExit("activation code not found")
    if args.expires_at:
        activation["expires_at"] = parse_dt(args.expires_at).isoformat()
    elif args.days:
        activation["expires_at"] = (datetime.now(UTC) + timedelta(days=args.days)).isoformat()
    if args.features:
        activation["features"] = parse_features(args.features)
    limits = parse_limits(args)
    if limits:
        activation["limits"] = limits
    if args.deployment_fingerprint:
        activation["deployment_fingerprint"] = args.deployment_fingerprint
    activation["updated_at"] = datetime.now(UTC).isoformat()
    append_audit(store, "renew", args.activation_code, public_activation(args.activation_code, activation))
    save_store(db_path, store)
    print(json.dumps(public_activation(args.activation_code, activation), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_export_license(args: argparse.Namespace) -> int:
    store = load_store(Path(args.db))
    license_record = None
    if args.license_id:
        license_record = store["licenses"].get(args.license_id)
    elif args.activation_code:
        activation = store["activations"].get(args.activation_code)
        if activation and activation.get("license_id"):
            license_record = store["licenses"].get(activation["license_id"])
    if not license_record:
        raise SystemExit("license not found; activate or refresh once before export")
    output = json.dumps(license_record["license"], ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def command_audit(args: argparse.Namespace) -> int:
    store = load_store(Path(args.db))
    items = list(reversed(store.get("audit", [])))[0 : args.limit]
    print(json.dumps({"items": items, "total": len(store.get("audit", []))}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    app = create_app(Path(args.db))
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sagitta Control License-Server-Center compatibility authority")
    parser.add_argument("--generate-keypair", action="store_true", help="print a new Ed25519 keypair and exit")
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create-activation", help="create or replace an activation code")
    create.add_argument("--db", default=DEFAULT_DB)
    create.add_argument("--activation-code", default="")
    create.add_argument("--customer-id", required=True)
    create.add_argument("--company-name", required=True)
    create.add_argument("--edition", default="enterprise")
    create.add_argument("--days", type=int, default=365)
    create.add_argument("--not-before", default="")
    create.add_argument("--expires-at", default="")
    create.add_argument("--features", default=",".join(DEFAULT_FEATURES))
    create.add_argument("--max-instances", type=int, default=0)
    create.add_argument("--max-users", type=int, default=0)
    create.add_argument("--deployment-fingerprint", default="")
    create.set_defaults(func=command_create_activation)

    status = subparsers.add_parser("set-status", help="set activation status: active/suspended/revoked")
    status.add_argument("--db", default=DEFAULT_DB)
    status.add_argument("--activation-code", required=True)
    status.add_argument("--status", choices=["active", "suspended", "revoked"], required=True)
    status.set_defaults(func=command_set_status)

    list_cmd = subparsers.add_parser("list", help="list activation ledger")
    list_cmd.add_argument("--db", default=DEFAULT_DB)
    list_cmd.set_defaults(func=command_list)

    renew = subparsers.add_parser("renew", help="renew/update an activation")
    renew.add_argument("--db", default=DEFAULT_DB)
    renew.add_argument("--activation-code", required=True)
    renew.add_argument("--days", type=int, default=0)
    renew.add_argument("--expires-at", default="")
    renew.add_argument("--features", default="")
    renew.add_argument("--max-instances", type=int, default=0)
    renew.add_argument("--max-users", type=int, default=0)
    renew.add_argument("--deployment-fingerprint", default="")
    renew.set_defaults(func=command_renew)

    export = subparsers.add_parser("export-license", help="export the last issued signed license")
    export.add_argument("--db", default=DEFAULT_DB)
    export.add_argument("--license-id", default="")
    export.add_argument("--activation-code", default="")
    export.add_argument("--out", default="")
    export.set_defaults(func=command_export_license)

    audit = subparsers.add_parser("audit", help="show authority audit events")
    audit.add_argument("--db", default=DEFAULT_DB)
    audit.add_argument("--limit", type=int, default=50)
    audit.set_defaults(func=command_audit)

    serve = subparsers.add_parser("serve", help="start the internal license authority API")
    serve.add_argument("--db", default=DEFAULT_DB)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8011)
    serve.set_defaults(func=command_serve)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generate_keypair:
        generate_keypair()
        return 0
    if not getattr(args, "command", None):
        raise SystemExit("choose a command, or use --generate-keypair")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
