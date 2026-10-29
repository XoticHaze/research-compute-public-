"""Choose an already-configured Cloudflare deploy token that can read account Worker routing.

Wrangler 4.x queries GET /accounts/{id}/workers/subdomain AFTER uploading
assets. Do not upload a partial console release when this exact permission is
missing. Never log a token, account ID, API body, or credential exception.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"
WORKER = "mmibkr-operator-console"


def _readable(token: str, account: str, path: str) -> bool:
    if not token or not account:
        return False
    req = Request(
        f"{API}/accounts/{account}/{path}",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                 "User-Agent": "mmibkr-console-worker-token-preflight"},
    )
    try:
        with urlopen(req, timeout=15) as response:
            if response.status != 200:
                return False
            raw = response.read(32769)
            if len(raw) > 32768:
                return False
            node = json.loads(raw)
            return type(node) is dict and node.get("success") is True
    except Exception:
        # Cloudflare API errors may echo account/token details; no raw logs.
        return False


def worker_token_ready(token: str, account: str) -> bool:
    return (_readable(token, account, "workers/subdomain")
            and _readable(token, account, f"workers/scripts/{WORKER}/settings"))


def select_route(account: str, scoped: str, legacy: str,
                 probe=None) -> str:
    if not account:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID_REQUIRED")
    if probe is None:
        probe = worker_token_ready
    if scoped and probe(scoped, account):
        return "scoped_r2"
    if legacy and probe(legacy, account):
        return "legacy_existing"
    raise ValueError("CLOUDFLARE_WORKERS_SUBDOMAIN_AUTH_REQUIRED")


def main() -> int:
    try:
        route = select_route(
            os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            os.environ.get("CLOUDFLARE_DEPLOY_TOKEN_R2", "").strip(),
            os.environ.get("CLOUDFLARE_LEGACY_WORKERS_TOKEN", "").strip(),
        )
    except ValueError as exc:
        raise SystemExit("MMIBKR_OPERATOR_CONSOLE_DEPLOY_TOKEN_PREFLIGHT=" + str(exc)) from None

    # Only the nonsecret route identifier crosses the GitHub step boundary.
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        raise SystemExit("MMIBKR_OPERATOR_CONSOLE_GITHUB_OUTPUT_REQUIRED")
    with Path(output_file).open("a", encoding="utf-8") as stream:
        stream.write("route=" + route + "\n")
    print("MMIBKR_OPERATOR_CONSOLE_DEPLOY_CREDENTIAL_ROUTE=" + route.upper())
    print("MMIBKR_OPERATOR_CONSOLE_WORKERS_SUBDOMAIN_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
