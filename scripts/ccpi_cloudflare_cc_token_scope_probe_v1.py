#!/usr/bin/env python3
"""CommandCenter-routed, public-GitHub-hosted Cloudflare credential readback.

Uses EXISTING repository secrets only. Does not install, deploy, mint keys,
write Cloudflare state, log bearer tokens, or claim admin/production admission.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"
ORIGINAL_ACCOUNT = "ce43cd7b917d98a4bb4866d30eed99c0"
NEUTRAL_ACCOUNT = "b33595eb85f346b0d1bf201810b4499a"
ALLOWED_HTTP = {200, 401, 403, 404, 429}


def status_for(token: str, path: str) -> int | str:
    if not token:
        return "NOT_CONFIGURED"
    if not path.startswith("/accounts/") and path != "/user/tokens/verify":
        raise ValueError("bounded_read_only_cloudflare_endpoint_required")
    request = Request(
        API + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "commandcenter-ccpi-owner-scope-readonly-v1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=12) as response:
            return response.status if response.status in ALLOWED_HTTP else "HTTP_OTHER"
    except HTTPError as exc:
        return exc.code if exc.code in ALLOWED_HTTP else "HTTP_OTHER"
    except (URLError, TimeoutError, OSError):
        return "TRANSPORT_UNAVAILABLE"


def summarize(token: str, account: str) -> dict:
    if not token:
        return {
            "configured": False, "verify_http": "NOT_CONFIGURED",
            "original_fleet_settings_http": "NOT_CONFIGURED",
            "neutral_owner_signer_settings_http": "NOT_CONFIGURED",
            "neutral_scripts_list_http": "NOT_CONFIGURED",
        }
    return {
        "configured": True,
        "verify_http": status_for(token, "/user/tokens/verify"),
        "original_fleet_settings_http": status_for(
            token, f"/accounts/{account}/workers/scripts/fleet-authority/settings"),
        "neutral_owner_signer_settings_http": status_for(
            token, f"/accounts/{NEUTRAL_ACCOUNT}/workers/scripts/ccpi-owner-cloudflare-authority/settings"),
        "neutral_scripts_list_http": status_for(
            token, f"/accounts/{NEUTRAL_ACCOUNT}/workers/scripts"),
    }


def main() -> None:
    account = os.environ.get("CC_CF_ORIGINAL_ACCOUNT", "").strip()
    if account != ORIGINAL_ACCOUNT or not re.fullmatch(r"[a-f0-9]{32}", account):
        raise SystemExit("CCPI_CF_PROBE_ORIGINAL_ACCOUNT_IDENTITY_UNVERIFIED")
    names = {
        "research_scoped_r2": "CC_CF_R2_TOKEN",
        "legacy_deploy": "CC_CF_LEGACY_TOKEN",
    }
    results = {
        "schema": "commandcenter.pi.owner_cloudflare_token_scope_readback.v1",
        "execution_route": "CC_GIT_FIRE_TO_PUBLIC_GITHUB_READONLY",
        "source": "existing_research_compute_public_cloudflare_secrets",
        "cloudflare_api_mutations": 0,
        "signer_key_issued": False,
        "production_deploy_attempted": False,
        "neutral_write_authorized_by_this_probe": False,
        "result_interpretation": (
            "HTTP read status proves only endpoint visibility; never grants "
            "neutral deployment, signing, or Pi root authorization"
        ),
        "token_routes": {
            name: summarize(os.environ.get(var, "").strip(), account)
            for name, var in names.items()
        },
    }
    out = Path(os.environ["CCPI_SCOPE_PROBE_RECEIPT"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("CCPI_CF_SCOPE_READONLY=PASS")
    for name, state in results["token_routes"].items():
        print(f"CCPI_CF_{name.upper()}_CONFIGURED={int(state['configured'])}")
        for field in ("verify_http","original_fleet_settings_http",
                      "neutral_owner_signer_settings_http","neutral_scripts_list_http"):
            print(f"CCPI_CF_{name.upper()}_{field.upper()}={state[field]}")


if __name__ == "__main__":
    main()
