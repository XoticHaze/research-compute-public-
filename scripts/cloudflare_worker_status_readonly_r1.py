"""Bounded SlenderIQ Cloudflare Worker observation, without deployment authority.

The public GitHub workflow owns the existing Cloudflare secrets. This module
never prints raw Cloudflare API payloads, API error bodies, account IDs, token
values, binding values, source bytes, or unapproved Worker names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

SCHEMA = "commandcenter.cloudflare_worker_readonly_receipt.r1"
REQUEST_SCHEMA = "commandcenter.cloudflare_worker_readonly_request.r1"
API = "https://api.cloudflare.com/client/v4"
WORKERS = frozenset({"mmibkr-operator-console", "fleet-authority"})
OPERATIONS = frozenset({"cloudflare.worker_status", "cloudflare.release_status"})
# Confirm presence only. Never export values or dynamic names from settings.
OBSERVED_BINDINGS = frozenset({
    "ACCESS_TEAM_DOMAIN", "ACCESS_AUD", "ACCESS_ALLOWED_EMAILS",
    "PI_OBSERVATION_PUBLISHER_APPROVED_SHA",
})
MAX_BODY = 131072
HEX32 = re.compile(r"[0-9a-fA-F]{32}\Z")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
SHA40 = re.compile(r"[0-9a-fA-F]{40}\Z")
REQUEST_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


def validate_request(obj: dict) -> tuple[str, str, str]:
    if not isinstance(obj, dict) or set(obj) != {"schema", "request_id", "operation", "worker"}:
        raise ValueError("REQUEST_SHAPE_REJECTED")
    if obj.get("schema") != REQUEST_SCHEMA:
        raise ValueError("REQUEST_SCHEMA_REJECTED")
    request_id, operation, worker = obj.get("request_id"), obj.get("operation"), obj.get("worker")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("REQUEST_ID_REJECTED")
    if operation not in OPERATIONS or worker not in WORKERS:
        raise ValueError("TARGET_OR_OPERATION_REJECTED")
    return request_id, operation, worker



class _RejectRedirect(HTTPRedirectHandler):
    """Forbid all redirect destinations; urllib otherwise forwards bearer auth."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("CLOUDFLARE_REDIRECT_REJECTED")


def urlopen(request, timeout=20):
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)



def api_get(account: str, token: str, path: str) -> dict:
    request = Request(
        API + "/accounts/" + account + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json",
                 "User-Agent": "commandcenter-cloudflare-readonly-r1"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("CLOUDFLARE_HTTP_ERROR")
            raw = response.read(MAX_BODY + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError("CLOUDFLARE_SCOPE_DENIED") from None
        if exc.code == 404:
            raise ValueError("WORKER_NOT_OBSERVED") from None
        raise ValueError("CLOUDFLARE_HTTP_ERROR") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("CLOUDFLARE_TRANSPORT_UNAVAILABLE") from None
    if len(raw) > MAX_BODY:
        raise ValueError("RESPONSE_TOO_LARGE")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("CLOUDFLARE_RESPONSE_INVALID") from None
    if not isinstance(parsed, dict) or parsed.get("success") is not True:
        raise ValueError("CLOUDFLARE_RESPONSE_REJECTED")
    return parsed


def worker_status(account: str, token: str, worker: str) -> dict:
    response = api_get(account, token, "/workers/scripts/" + worker + "/settings")
    root = response.get("result")
    if not isinstance(root, dict) or not isinstance(root.get("bindings"), list):
        raise ValueError("WORKER_SETTINGS_SHAPE_REJECTED")
    bindings = root["bindings"]
    if len(bindings) > 100 or any(not isinstance(x, dict) for x in bindings):
        raise ValueError("WORKER_BINDINGS_SHAPE_REJECTED")
    seen = set()
    for item in bindings:
        name = item.get("name")
        if not isinstance(name, str) or len(name) > 128 or name in seen:
            raise ValueError("WORKER_BINDINGS_SHAPE_REJECTED")
        seen.add(name)
    return {
        "status": "WORKER_SETTINGS_OBSERVED_NOT_SOURCE_ATTESTED",
        "binding_count": len(bindings),
        "approved_binding_presence": {name: name in seen for name in sorted(OBSERVED_BINDINGS)},
        "unreported_binding_count": len(seen - OBSERVED_BINDINGS),
    }


def release_status(account: str, token: str, worker: str) -> dict:
    response = api_get(account, token, "/workers/scripts/" + worker + "/deployments?per_page=1")
    root = response.get("result")
    deployments = root.get("deployments") if isinstance(root, dict) else None
    if not isinstance(deployments, list) or not deployments:
        raise ValueError("ACTIVE_DEPLOYMENT_NOT_OBSERVED")
    top = deployments[0]
    if not isinstance(top, dict) or not UUID.fullmatch(str(top.get("id") or "")):
        raise ValueError("DEPLOYMENT_SHAPE_REJECTED")
    versions = top.get("versions")
    if not isinstance(versions, list) or not 1 <= len(versions) <= 10:
        raise ValueError("DEPLOYMENT_VERSIONS_REJECTED")
    weights, identities = [], []
    for row in versions:
        if not isinstance(row, dict) or not UUID.fullmatch(str(row.get("version_id") or "")):
            raise ValueError("DEPLOYMENT_VERSIONS_REJECTED")
        weight = row.get("percentage")
        if isinstance(weight, bool) or not isinstance(weight, (float, int)) or not (0 < weight <= 100):
            raise ValueError("DEPLOYMENT_VERSIONS_REJECTED")
        weights.append(float(weight))
        identities.append(str(row["version_id"]).lower())
    if abs(sum(weights) - 100) > 0.01 or len(identities) != len(set(identities)):
        raise ValueError("DEPLOYMENT_PERCENTAGE_REJECTED")
    created = top.get("created_on")
    if not isinstance(created, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", created):
        raise ValueError("DEPLOYMENT_DATE_REJECTED")
    fingerprint = hashlib.sha256(
        json.dumps(sorted(zip(identities, weights)), separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "ACTIVE_DEPLOYMENT_OBSERVED_NOT_SOURCE_ATTESTED",
        "created_on_utc": created,
        "active_version_count": len(weights),
        "active_percentages": sorted(weights, reverse=True),
        "active_version_set_sha256": fingerprint,
        "single_version_100_percent": len(weights) == 1 and weights[0] == 100,
    }


def execute(request: dict, env: dict) -> tuple[dict, bool]:
    # Validation always occurs before credential lookup or any external request.
    rid, operation, worker = validate_request(request)
    receipt = {
        "schema": SCHEMA,
        "request_id": rid,
        "operation": operation,
        "account_label": "slenderiq",
        "worker": worker,
        "read_only": True,
        "mutation_performed": False,
        "secret_values_emitted": False,
        "result": {},
    }
    account = env.get("CF_ACCOUNT_ID", "").strip()
    token = env.get("CF_READ_TOKEN", "").strip()
    if not HEX32.fullmatch(account) or not token:
        receipt["result"] = {"status": "EXISTING_READ_CREDENTIAL_UNAVAILABLE"}
        return receipt, False
    try:
        observation = (worker_status if operation == "cloudflare.worker_status" else release_status)(account, token, worker)
    except ValueError as exc:
        receipt["result"] = {"status": str(exc)}
        return receipt, False
    receipt["result"] = observation
    return receipt, True


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request-file", type=Path)
    group.add_argument("--operation", choices=sorted(OPERATIONS))
    parser.add_argument("--worker", choices=sorted(WORKERS))
    parser.add_argument("--request-id")
    parser.add_argument("--receipt-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.request_file:
            if args.worker or args.request_id:
                raise ValueError("REQUEST_MODE_MIXED")
            if args.request_file.stat().st_size > 4096:
                raise ValueError("REQUEST_TOO_LARGE")
            data = json.loads(args.request_file.read_text(encoding="utf-8"))
        else:
            if not args.worker or not args.request_id:
                raise ValueError("REQUEST_MISSING_FIELD")
            data = {"schema": REQUEST_SCHEMA, "operation": args.operation,
                    "worker": args.worker, "request_id": args.request_id}
        receipt, ok = execute(data, os.environ)
    except (ValueError, OSError, UnicodeError) as exc:
        # Keep parsing messages and request contents out of public logs.
        print("CLOUDFLARE_READONLY_REQUEST_REJECTED=1")
        return 2
    args.receipt_file.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_file.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("CLOUDFLARE_READONLY_RECEIPT_STATUS=" + receipt["result"]["status"])
    print("CLOUDFLARE_READONLY_MUTATIONS=0")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
