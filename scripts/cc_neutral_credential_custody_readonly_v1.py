#!/usr/bin/env python3
"""CommandCenter neutral Cloudflare credential-custody metadata audit.

Runs only in the existing public READ-ONLY scope workflow using its already
present limited Cloudflare gateway credential. No broad neutral administrator
bearer is requested, read, minted, printed, or moved. No CF mutations.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ACCOUNT = "b33595eb85f346b0d1bf201810b4499a"
STORE = "3bdb660e7b8d4de6a1688f922f3991f7"
OWNER_ADMIN = "CC-SHARED-WORKER-DEPLOY"
BROKER_SECRET = "BROKER_EDITOR_TOKEN"
MAINTAINER = "reference-release-maintainer-v1"
API = "https://api.cloudflare.com/client/v4"
OUTPUT = Path("/tmp/cc-neutral-credential-custody-readonly.json")
PATHS = {
    "store_list": f"/accounts/{ACCOUNT}/secrets_store/stores",
    "store_secret_metadata": f"/accounts/{ACCOUNT}/secrets_store/stores/{STORE}/secrets",
    "maintainer_bindings": f"/accounts/{ACCOUNT}/workers/scripts/{MAINTAINER}/settings",
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def read_only_api(token: str, path: str) -> tuple[int | str, dict]:
    # Reject invented paths, redirects and any non-GET action before contact.
    if path not in PATHS.values():
        raise ValueError("non_allowlisted_neutral_read")
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json",
                 "User-Agent": "commandcenter-neutral-credential-custody-readonly-v1"},
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=12) as response:
            status = response.status
            raw = response.read(131073)
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "UNAVAILABLE", {}
    if status != 200 or len(raw) > 131072:
        return status, {}
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return status, {}
    return status, data if isinstance(data, dict) else {}

def rows_from(result: dict) -> list[dict] | None:
    if result.get("success") is not True:
        return None
    data = result.get("result")
    if isinstance(data, dict) and isinstance(data.get("secrets"), list):
        data = data["secrets"]
    if isinstance(data, dict) and isinstance(data.get("stores"), list):
        data = data["stores"]
    if not isinstance(data, list) or len(data) > 1000:
        return None
    return [x for x in data if isinstance(x, dict)]

def examine(call) -> dict:
    """Only boolean/HTTP status metadata escapes; absence is never authority proof."""
    receipt = {
        "schema": "commandcenter.cloudflare.neutral_credential_custody_readonly.v1",
        "account_role": "SHARED_COMPUTE_NEUTRAL_AUTHORIZATION_ONLY",
        "existing_owner_user_token_observed_in_ui": True,
        "existing_owner_token_name": OWNER_ADMIN,
        "existing_owner_token_broad_worker_admin": True,
        "existing_owner_token_secret_value_available": False,
        "existing_owner_token_executor_custody_proven": False,
        "existing_owner_token_binding_proven": False,
        "token_issuer_rights_proven": False,
        "store_list_http": "NOT_RUN",
        "known_store_metadata_visible": False,
        "store_secret_list_http": "NOT_RUN",
        "owner_token_exact_named_secret_metadata_visible": False,
        "broker_editor_exact_named_secret_metadata_visible": False,
        "maintainer_settings_http": "NOT_RUN",
        "maintainer_owner_admin_binding_visible": False,
        "maintainer_broker_editor_binding_visible": False,
        "secret_values_read_or_exported": False,
        "cloudflare_mutations": 0,
        "source_account_matches_neutral": True,
        "conclusion": "NOT_VERIFIED",
    }
    for key, path in PATHS.items():
        status, node = call(path)
        if type(status) is not int or status < 100 or status > 599:
            status = "UNAVAILABLE"
        receipt[{"store_list": "store_list_http",
                 "store_secret_metadata": "store_secret_list_http",
                 "maintainer_bindings": "maintainer_settings_http"}[key]] = status
        if status != 200 or node.get("success") is not True:
            continue
        if key == "store_list":
            stores = rows_from(node)
            receipt["known_store_metadata_visible"] = bool(
                stores is not None and any(x.get("id") == STORE for x in stores))
        elif key == "store_secret_metadata":
            secrets = rows_from(node)
            if secrets is not None:
                receipt["owner_token_exact_named_secret_metadata_visible"] = any(
                    x.get("name") == OWNER_ADMIN for x in secrets)
                receipt["broker_editor_exact_named_secret_metadata_visible"] = any(
                    x.get("name") == BROKER_SECRET for x in secrets)
        else:
            data = node.get("result")
            if not isinstance(data, dict):
                continue
            rows = data.get("bindings")
            if not isinstance(rows, list) or len(rows) > 200:
                continue
            receipt["maintainer_owner_admin_binding_visible"] = any(
                isinstance(b, dict) and b.get("name") == OWNER_ADMIN
                and b.get("type") in ("secret_text", "secrets_store_secret") for b in rows)
            receipt["maintainer_broker_editor_binding_visible"] = any(
                isinstance(b, dict) and b.get("name") == BROKER_SECRET
                and b.get("type") in ("secret_text", "secrets_store_secret") for b in rows)
    # Names/bindings are metadata, not proof the token's actual bearer is stored.
    if any(receipt[k] == 200 for k in (
            "store_list_http", "store_secret_list_http", "maintainer_settings_http")):
        receipt["conclusion"] = "PARTIAL_METADATA_ONLY_NOT_BEARER_OR_EXECUTOR_PROOF"
    else:
        receipt["conclusion"] = "GATEWAY_CREDENTIAL_METADATA_SCOPE_INSUFFICIENT_OR_UNAVAILABLE"
    return receipt

def main() -> int:
    account = os.environ.get("CLOUDFLARE_GATEWAY_ACCOUNT_ID", "").strip().lower()
    token = os.environ.get("CLOUDFLARE_GATEWAY_ACCESS_TOKEN", "").strip()
    if account != ACCOUNT or not (20 <= len(token) <= 1000) or re.search(r"[\r\n\0]", token):
        record = {
            "schema": "commandcenter.cloudflare.neutral_credential_custody_readonly.v1",
            "conclusion": "EXISTING_LIMITED_GATEWAY_CREDENTIAL_NOT_CONFIGURED_IN_THIS_RUN",
            "account_role": "SHARED_COMPUTE_NEUTRAL_AUTHORIZATION_ONLY",
            "credential_values_exported": False,
            "cloudflare_mutations": 0,
        }
    else:
        record = examine(lambda path: read_only_api(token, path))
    OUTPUT.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(record, sort_keys=True))
    print("CC_NEUTRAL_TOKEN_CUSTODY_READONLY_METADATA=COMPLETE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
