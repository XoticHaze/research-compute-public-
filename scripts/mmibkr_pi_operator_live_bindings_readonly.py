#!/usr/bin/env python3
"""Existing MM-IBKR Operator Worker deployed Pi-data ingress binding audit.

No credential values, account identifiers, balances, stored financial records,
Access tokens or actual Worker inputs are emitted. Fixed GET only; neither
binding presence nor static source means live financial data is served.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TARGET = "mmibkr-operator-console"
API = "https://api.cloudflare.com/client/v4"
EXPECTED = (
    "OPERATOR_STATE", "PI_OWNER_APPROVER", "ASSETS",
    "PI_OBSERVATION_PUBLISHER_APPROVED_SHA", "PI_BOT_PRIVATE_SOURCE_BINDING",
    "PI_LIVE_FINANCE_INGEST_ENABLED", "PI_LIVE_FINANCE_ORIGIN_ADMITTED",
    "PI_LIVE_FINANCE_HMAC_KEY", "PI_LIVE_EXPECTED_ACCOUNT_SHA256",
    "PI_LIVE_FINANCE_ACCESS_AUD", "PI_LIVE_FINANCE_SERVICE_CLIENT_ID",
)
FLAGS = ("PI_LIVE_FINANCE_INGEST_ENABLED", "PI_LIVE_FINANCE_ORIGIN_ADMITTED")
SCHEMA = "commandcenter.mmibkr.existing_pi_operator_bindings_readonly.v1"


def summarize_bindings(doc: dict) -> dict:
    result = doc.get("result") if isinstance(doc, dict) and doc.get("success") is True else None
    if not isinstance(result, dict):
        return {"settings_valid": False, "bindings": {},
                "finance_flags": {}, "private_pi_publish_admitted": False,
                "private_finance_origin_admitted": False,
                "real_pi_data_served_verified": False}
    raw = result.get("bindings") or []
    if not isinstance(raw, list):
        raw = []
    found = {x["name"]: x for x in raw if isinstance(x, dict)
             and isinstance(x.get("name"), str) and x.get("name") in EXPECTED}
    flags = {
        k: (str(found[k].get("text"))
            if k in found and found[k].get("type") == "plain_text"
            and str(found[k].get("text")) in ("0", "1") else "UNVERIFIED")
        for k in FLAGS
    }
    return {
        "settings_valid": True,
        "bindings": {k: (k in found) for k in EXPECTED},
        "finance_flags": flags,
        "private_pi_publish_admitted": (
            "PI_OBSERVATION_PUBLISHER_APPROVED_SHA" in found and
            "PI_BOT_PRIVATE_SOURCE_BINDING" in found),
        "private_finance_origin_admitted": (
            flags.get("PI_LIVE_FINANCE_INGEST_ENABLED") == "1" and
            flags.get("PI_LIVE_FINANCE_ORIGIN_ADMITTED") == "1" and
            all(k in found for k in (
                "PI_LIVE_FINANCE_HMAC_KEY", "PI_LIVE_EXPECTED_ACCOUNT_SHA256",
                "PI_LIVE_FINANCE_ACCESS_AUD", "PI_LIVE_FINANCE_SERVICE_CLIENT_ID"))),
        "real_pi_data_served_verified": False,
    }


def read_settings(account: str, token: str) -> tuple[int | str, dict]:
    if not token:
        return "NOT_CONFIGURED", {}
    url = API + "/accounts/" + account + "/workers/scripts/" + TARGET + "/settings"
    req = Request(url, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "commandcenter-live-pi-binding-readonly-v1",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read(160000)
    except HTTPError as exc:
        return exc.code, {}
    except (URLError, TimeoutError, OSError):
        return "UNAVAILABLE", {}
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError):
        return status, {}
    return status, doc if isinstance(doc, dict) else {}


def main() -> int:
    account = os.environ.get("CC_CF_ORIGINAL_ACCOUNT", "").strip()
    if len(account) != 32 or any(c not in "0123456789abcdef" for c in account):
        raise SystemExit("ORIGINAL_ACCOUNT_NOT_PINNED")
    routes = [
        ("research_scoped_r2", os.environ.get("CC_CF_R2_TOKEN", "").strip()),
        ("legacy_existing", os.environ.get("CC_CF_LEGACY_TOKEN", "").strip()),
    ]
    report = {
        "schema": SCHEMA,
        "target": TARGET,
        "authority": "READ_ONLY_DEPLOYED_METADATA_NOT_AUTHENTICATED_PI_DATA",
        "cloudflare_mutations": 0,
        "tokens_or_accounts_exported": False,
        "broker_data_exported": False,
        "results": {},
    }
    for label, token in routes:
        http, response = read_settings(account, token)
        report["results"][label] = {
            "settings_http": http,
            **summarize_bindings(response),
        }
    print(json.dumps(report, sort_keys=True))
    if not any(v["settings_http"] == 200 and v["settings_valid"]
               for v in report["results"].values()):
        print("MMIBKR_PI_OPERATOR_SETTINGS=HOLD_NO_VERIFIED_READ")
    else:
        print("MMIBKR_PI_OPERATOR_SETTINGS=READONLY_READBACK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
