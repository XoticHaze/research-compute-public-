from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"


def api(token: str, method: str, url: str, *, body: bytes | None = None, content_type: str | None = None):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "reference-neutral-control-plane-existing-deploy-r1",
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        node = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        node = {"raw": raw[:512].decode("utf-8", "replace")}
    return status, node


def multipart(metadata: dict, file_path: Path):
    boundary = "----cc-" + secrets.token_hex(16)
    parts: list[bytes] = []

    def add(headers: list[str], payload: bytes):
        parts.append(("--" + boundary + "\r\n").encode())
        parts.append(("\r\n".join(headers) + "\r\n\r\n").encode())
        parts.append(payload)
        parts.append(b"\r\n")

    add(
        ['Content-Disposition: form-data; name="metadata"', 'Content-Type: application/json'],
        json.dumps(metadata, separators=(",", ":")).encode(),
    )
    add(
        [
            'Content-Disposition: form-data; name="index.js"; filename="index.js"',
            "Content-Type: application/javascript+module",
        ],
        file_path.read_bytes(),
    )
    parts.append(("--" + boundary + "--\r\n").encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def deny_broker(account: str, token: str):
    url = f"{API}/accounts/{account}/workers/scripts/reference-release-broker-v1/settings"
    status, _ = api(token, "GET", url)
    if status == 200:
        raise SystemExit("EXISTING_DEPLOY_CREDENTIAL_CAN_ADMINISTER_BROKER=1")
    if status not in {401, 403, 404}:
        raise SystemExit(f"Unexpected broker denial status: {status}")
    print("REFERENCE_EXISTING_DEPLOY_BROKER_DENY_PASS=1")


def upload_version(account: str, token: str, worker: str, source: Path, metadata: dict):
    query = urlencode({"bindings_inherit": "strict"})
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/versions?{query}"
    body, content_type = multipart(metadata, source)
    status, node = api(token, "POST", url, body=body, content_type=content_type)
    if status not in {200, 201} or node.get("success") is not True:
        raise SystemExit(f"{worker} version upload failed HTTP {status}: {json.dumps(node)[:1000]}")
    result = node.get("result") or {}
    version_id = str(result.get("id") or "")
    if not version_id:
        raise SystemExit(f"{worker} version id missing")
    reconciliation = result.get("exports_reconciliation") or {}
    if reconciliation.get("deleted"):
        raise SystemExit(f"{worker} unexpected Durable Object delete: {reconciliation['deleted']}")
    print(worker.upper().replace("-", "_") + "_VERSION_UPLOADED=1")
    return version_id


def deploy_version(account: str, token: str, worker: str, version_id: str):
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/deployments"
    payload = json.dumps(
        {
            "strategy": "percentage",
            "versions": [{"version_id": version_id, "percentage": 100}],
            "annotations": {"workers/message": "reference neutral control plane bootstrap r1"},
        },
        separators=(",", ":"),
    ).encode()
    status, node = api(token, "POST", url, body=payload, content_type="application/json")
    if status not in {200, 201} or node.get("success") is not True:
        raise SystemExit(f"{worker} deployment failed HTTP {status}: {json.dumps(node)[:1000]}")
    print(worker.upper().replace("-", "_") + "_DEPLOYED=1")


def prove_settings(account: str, token: str, worker: str, required: set[str]):
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/settings"
    status, node = api(token, "GET", url)
    if status != 200 or node.get("success") is not True or not isinstance(node.get("result"), dict):
        raise SystemExit(f"{worker} settings proof failed HTTP {status}: {json.dumps(node)[:1000]}")
    bindings = node["result"].get("bindings") or []
    names = {str(x.get("name") or "") for x in bindings if isinstance(x, dict)}
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"{worker} missing bindings: {missing}")
    print(worker.upper().replace("-", "_") + "_SETTINGS_PASS=1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise SystemExit("Cloudflare bootstrap credentials missing")

    root = Path(args.repo_root).resolve()
    authority_source = root / "cloudflare/reference-maintenance-authority/src/index.js"
    maintainer_source = root / "cloudflare/reference-release-maintainer/src/index.js"

    deny_broker(account, token)

    authority_meta = {
        "main_module": "index.js",
        "compatibility_date": "2026-09-27",
        "annotations": {"workers/message": "reference maintenance authority bootstrap r1"},
        "bindings": [
            {
                "type": "service",
                "name": "MAINTAINER",
                "service": "reference-release-maintainer-v1",
                "environment": "production",
            },
            {
                "type": "durable_object_namespace",
                "name": "AUTHORITY_STATE",
                "class_name": "AuthorityState",
            },
        ],
        "exports": {
            "AuthorityState": {"type": "durable-object", "storage": "sqlite"}
        },
    }
    authority_version = upload_version(
        account,
        token,
        "reference-maintenance-authority-v1",
        authority_source,
        authority_meta,
    )
    deploy_version(account, token, "reference-maintenance-authority-v1", authority_version)

    maintainer_meta = {
        "main_module": "index.js",
        "compatibility_date": "2026-09-27",
        "annotations": {"workers/message": "reference release maintainer bootstrap r1"},
        "bindings": [
            {"type": "inherit", "name": "BROKER_EDITOR_TOKEN", "version_id": "latest"},
            {"type": "inherit", "name": "CLOUDFLARE_ACCOUNT_ID", "version_id": "latest"},
            {
                "type": "service",
                "name": "MAINTENANCE_AUTHORITY",
                "service": "reference-maintenance-authority-v1",
                "environment": "production",
            },
            {
                "type": "durable_object_namespace",
                "name": "MAINTENANCE_LEDGER",
                "class_name": "MaintenanceLedger",
            },
        ],
        "exports": {
            "MaintenanceLedger": {"type": "durable-object", "storage": "sqlite"}
        },
    }
    maintainer_version = upload_version(
        account,
        token,
        "reference-release-maintainer-v1",
        maintainer_source,
        maintainer_meta,
    )
    deploy_version(account, token, "reference-release-maintainer-v1", maintainer_version)

    prove_settings(
        account,
        token,
        "reference-maintenance-authority-v1",
        {"AUTHORITY_STATE", "MAINTAINER"},
    )
    prove_settings(
        account,
        token,
        "reference-release-maintainer-v1",
        {"BROKER_EDITOR_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "MAINTENANCE_AUTHORITY", "MAINTENANCE_LEDGER"},
    )
    deny_broker(account, token)

    print("REFERENCE_NEUTRAL_CONTROL_PLANE_BOOTSTRAP_PASS=1")
    print("EXISTING_DEPLOY_CREDENTIAL_RENARROW_REQUIRED=1")


if __name__ == "__main__":
    main()
