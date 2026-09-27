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


def put_worker_secret(account: str, token: str, worker: str, name: str, value: str):
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/secrets"
    payload = json.dumps({
        "name": name,
        "text": value,
        "type": "secret_text",
    }, separators=(",", ":")).encode()
    status, node = api(
        token,
        "PUT",
        url,
        body=payload,
        content_type="application/json",
    )
    if status != 200 or node.get("success") is not True:
        raise SystemExit(
            f"{worker} secret binding update failed HTTP {status}: "
            + json.dumps(node)[:1000]
        )
    print(worker.upper().replace("-", "_") + "_" + name + "_SECRET_BOUND=1")


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


def broker_preseal_gate(account: str, token: str):
    url = f"{API}/accounts/{account}/workers/scripts/reference-release-broker-v1/settings"
    status, node = api(token, "GET", url)
    if status in {401, 403, 404}:
        print("REFERENCE_EXISTING_DEPLOY_BROKER_DENY_PASS=1")
        return False
    if status != 200:
        raise SystemExit(f"Unexpected broker settings status: {status}")
    result = node.get("result") if isinstance(node.get("result"), dict) else {}
    bindings = result.get("bindings") or []
    names = {
        str(row.get("name") or "")
        for row in bindings
        if isinstance(row, dict)
    }
    sensitive = {
        "BROKER_SIGNING_PRIVATE_JWK",
        "AUTHORITY_PUBLIC_B64",
        "GRANT_LEDGER",
    }
    present = sorted(sensitive & names)
    if present:
        raise SystemExit(
            "BROKER_PRESEAL_GATE_REJECTED_SENSITIVE_BINDINGS=" + ",".join(present)
        )
    print("EXISTING_DEPLOY_CREDENTIAL_CAN_ADMINISTER_BROKER=1")
    print("REFERENCE_BROKER_PRESEAL_EMPTY_PASS=1")
    return True


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

    verify_url = f"{API}/accounts/{account}/tokens/verify"
    verify_status, verify_node = api(token, "GET", verify_url)
    owner = "account"
    if verify_status != 200 or verify_node.get("success") is not True:
        verify_status, verify_node = api(token, "GET", f"{API}/user/tokens/verify")
        owner = "user"
    verify_result = verify_node.get("result") if isinstance(verify_node.get("result"), dict) else {}
    token_id = str(verify_result.get("id") or "")
    token_status = str(verify_result.get("status") or "")
    print("EXISTING_DEPLOY_TOKEN_OWNER=" + owner)
    print("EXISTING_DEPLOY_TOKEN_ID=" + token_id)
    print("EXISTING_DEPLOY_TOKEN_STATUS=" + token_status)
    if token_id:
        details_path = f"{API}/user/tokens/{token_id}" if owner == "user" else f"{API}/accounts/{account}/tokens/{token_id}"
        details_status, details_node = api(token, "GET", details_path)
        details = details_node.get("result") if isinstance(details_node.get("result"), dict) else {}
        if details_status == 200 and details_node.get("success") is True:
            print("EXISTING_DEPLOY_TOKEN_NAME=" + str(details.get("name") or ""))
        else:
            print("EXISTING_DEPLOY_TOKEN_DETAILS_HTTP=" + str(details_status))

    broad_preseal = broker_preseal_gate(account, token)

    put_worker_secret(
        account,
        token,
        "reference-release-maintainer-v1",
        "CLOUDFLARE_ACCOUNT_ID",
        account,
    )

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
    print("REFERENCE_MAINTENANCE_AUTHORITY_NAMESPACE_PROVISIONED=1")

    authority_bound_meta = dict(authority_meta)
    authority_bound_meta["bindings"] = list(authority_meta["bindings"]) + [{
        "type": "durable_object_namespace",
        "name": "AUTHORITY_STATE",
        "class_name": "AuthorityState",
    }]
    authority_bound_version = upload_version(
        account,
        token,
        "reference-maintenance-authority-v1",
        authority_source,
        authority_bound_meta,
    )
    deploy_version(
        account,
        token,
        "reference-maintenance-authority-v1",
        authority_bound_version,
    )

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
    print("REFERENCE_RELEASE_MAINTAINER_NAMESPACE_PROVISIONED=1")

    maintainer_bound_meta = dict(maintainer_meta)
    maintainer_bound_meta["bindings"] = list(maintainer_meta["bindings"]) + [{
        "type": "durable_object_namespace",
        "name": "MAINTENANCE_LEDGER",
        "class_name": "MaintenanceLedger",
    }]
    maintainer_bound_version = upload_version(
        account,
        token,
        "reference-release-maintainer-v1",
        maintainer_source,
        maintainer_bound_meta,
    )
    deploy_version(
        account,
        token,
        "reference-release-maintainer-v1",
        maintainer_bound_version,
    )

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
    broker_preseal_gate(account, token)

    print("REFERENCE_NEUTRAL_CONTROL_PLANE_BOOTSTRAP_PASS=1")
    if broad_preseal:
        print("EXISTING_DEPLOY_CREDENTIAL_RENARROW_REQUIRED=1")
    else:
        print("EXISTING_DEPLOY_CREDENTIAL_ALREADY_BROKER_DENIED=1")


if __name__ == "__main__":
    main()
