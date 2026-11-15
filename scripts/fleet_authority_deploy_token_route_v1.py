"""Select an existing Fleet Authority deployment credential that satisfies Wrangler.

The scoped Cloudflare R2 token can read the Fleet Worker but cannot necessarily
read account /workers/subdomain. That endpoint is queried AFTER upload. Probe
both existing credentials before running Wrangler and never log their values.
"""
from __future__ import annotations
import os
from pathlib import Path

from scripts.mmibkr_operator_console_deploy_token_route_v1 import _readable

WORKER = "fleet-authority"


def worker_token_ready(token: str, account: str) -> bool:
    return (_readable(token, account, "workers/subdomain")
            and _readable(token, account, "workers/scripts/" + WORKER + "/settings"))


def select_route(account: str, scoped: str, legacy: str, probe=None) -> str:
    if not account:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID_REQUIRED")
    ready = probe or worker_token_ready
    if scoped and ready(scoped, account):
        return "scoped_r2"
    if legacy and ready(legacy, account):
        return "legacy_existing"
    raise ValueError("CLOUDFLARE_FLEET_WORKERS_SUBDOMAIN_AUTH_REQUIRED")


def main() -> int:
    try:
        route = select_route(
            os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
            os.environ.get("CLOUDFLARE_DEPLOY_TOKEN_R2", "").strip(),
            os.environ.get("CLOUDFLARE_LEGACY_WORKERS_TOKEN", "").strip(),
        )
    except ValueError as e:
        raise SystemExit("FLEET_AUTHORITY_DEPLOY_PREFLIGHT=" + str(e)) from None
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise SystemExit("FLEET_AUTHORITY_GITHUB_OUTPUT_REQUIRED")
    with Path(output).open("a", encoding="utf-8") as stream:
        stream.write("route=" + route + "\n")
    print("FLEET_AUTHORITY_SELECTED_DEPLOY_ROUTE=" + route.upper())
    print("FLEET_AUTHORITY_WORKERS_SUBDOMAIN_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
