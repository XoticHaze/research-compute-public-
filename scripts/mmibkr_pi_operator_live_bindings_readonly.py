#!/usr/bin/env python3
"""Existing MM-IBKR Operator Worker deployed Pi-data ingress binding audit.

No credential values, account identifiers, balances, stored financial records,
Access tokens or actual Worker inputs are emitted. Fixed GET only; neither
binding presence nor static source means live financial data is served.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener

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


# Existing original-account Access metadata only. No token list, issuance,
# secret retrieval, policy update, bearer forwarding, or browser admission.
ORIGINAL_ACCOUNT = "ce43cd7b917d98a4bb4866d30eed99c0"
OPERATOR_HOST = "mmibkr-operator-console.slenderiq.workers.dev"
FINANCE_PATH = OPERATOR_HOST + "/v1/pi-live-financial"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def access_get(account, token, suffix):
    if account != ORIGINAL_ACCOUNT or not token:
        return "NOT_ADMITTED", {}
    allowed = (
        re.fullmatch(r"/access/apps\?page=[1-5]&per_page=100", suffix)
        or re.fullmatch(r"/access/apps/" + UUID.pattern + r"/policies\?page=[1-5]&per_page=100", suffix)
        or re.fullmatch(r"/access/service_tokens/" + UUID.pattern, suffix)
    )
    if not allowed:
        raise ValueError("ACCESS_METADATA_GET_PATH_NOT_ADMITTED")
    request = Request(API + "/accounts/" + account + suffix, method="GET",
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/json",
                               "User-Agent": "commandcenter-operator-access-readonly-v1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            http, raw = response.status, response.read(1000001)
    except HTTPError as exc:
        return exc.code, {}
    except (URLError, TimeoutError, OSError):
        return "UNAVAILABLE", {}
    if len(raw) > 1000000:
        return "RESPONSE_LIMIT", {}
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError):
        return http, {}
    return http, doc if type(doc) is dict else {}


def access_pages(account, token, path):
    rows = []
    for page in range(1, 6):
        http, doc = access_get(account, token, path + f"?page={page}&per_page=100")
        if http != 200 or doc.get("success") is not True or type(doc.get("result")) is not list:
            return http, [], False
        part = doc["result"]
        if len(part) > 100 or any(type(row) is not dict for row in part):
            return "INVALID_RESPONSE", [], False
        rows.extend(part)
        info = doc.get("result_info")
        if type(info) is not dict:
            return http, [], False
        total_pages = info.get("total_pages")
        total_count = info.get("total_count")
        if type(total_pages) is int and 0 <= total_pages <= page:
            if type(total_count) is int and total_count != len(rows):
                return http, [], False
            return http, rows, True
        if type(total_count) is int and total_count == len(rows):
            return http, rows, True
        if not part:
            return http, [], False
    return "PAGE_LIMIT", [], False


def app_uris(app):
    # Prefer documented destinations. Non-URI Worker/global destinations
    # are not interpreted as an exact path and must not establish absence.
    dests = app.get("destinations")
    if type(dests) is list and dests:
        values = [x.get("uri") for x in dests if type(x) is dict
                  and x.get("type", "public") == "public"]
        unknown = any(type(x) is not dict or x.get("type", "public") != "public"
                      or bool(x.get("overrides")) or type(x.get("uri")) is not str for x in dests)
    else:
        values = [app.get("domain")]
        legacy = app.get("self_hosted_domains")
        if type(legacy) is list:
            values.extend(legacy)
        unknown = False
    normalized = set()
    for value in values:
        if type(value) is str:
            normalized.add(value.removeprefix("https://").rstrip("/"))
    return normalized, unknown


def exact_token_policy(policies):
    # Return token identity in memory only. Never serialize this value.
    if len(policies) != 1:
        return None
    p = policies[0]
    rules = p.get("include")
    if (p.get("decision") != "non_identity" or type(rules) is not list or len(rules) != 1
            or p.get("require") not in (None, []) or p.get("exclude") not in (None, [])):
        return None
    rule = rules[0]
    if type(rule) is not dict or set(rule) != {"service_token"}:
        return None
    selector = rule["service_token"]
    token_id = selector.get("token_id") if type(selector) is dict else None
    return token_id if type(token_id) is str and UUID.fullmatch(token_id) else None


def inspect_finance_access(account, token):
    report = {
        "apps_http": "UNVERIFIED", "complete_app_inventory": False,
        "exact_finance_app_count": None, "exact_human_host_app_count": None,
        "non_uri_or_override_scope_present": None, "policies_http": "UNVERIFIED",
        "exact_single_service_token_policy": False, "distinct_machine_audience": False,
        "service_auth_401": False, "token_metadata_http": "UNVERIFIED",
        "linked_service_token_enabled_unexpired": False,
        "root_secret_custody_verified": False, "machine_post_verified": False,
    }
    http, apps, complete = access_pages(account, token, "/access/apps")
    report.update(apps_http=http, complete_app_inventory=complete)
    if not complete:
        return report
    machine, human = [], []
    non_uri = False
    for app in apps:
        uris, unknown = app_uris(app)
        non_uri |= unknown
        if FINANCE_PATH in uris:
            machine.append((app, uris, unknown))
        if OPERATOR_HOST in uris:
            human.append(app)
    report.update(exact_finance_app_count=len(machine), exact_human_host_app_count=len(human),
                  non_uri_or_override_scope_present=non_uri)
    if len(machine) != 1:
        return report
    app, uris, unknown = machine[0]
    aid, aud = app.get("id"), app.get("aud")
    if (unknown or uris != {FINANCE_PATH} or app.get("type") != "self_hosted"
            or type(aid) is not str or not UUID.fullmatch(aid)):
        return report
    report["service_auth_401"] = app.get("service_auth_401_redirect") is True
    report["distinct_machine_audience"] = (
        type(aud) is str and bool(re.fullmatch(r"[0-9a-f]{64}", aud))
        and len(human) == 1 and type(human[0].get("aud")) is str
        and human[0]["aud"] != aud)
    http, policies, complete = access_pages(account, token, "/access/apps/" + aid + "/policies")
    report["policies_http"] = http
    token_id = exact_token_policy(policies) if complete else None
    report["exact_single_service_token_policy"] = token_id is not None
    if token_id is None:
        return report
    http, doc = access_get(account, token, "/access/service_tokens/" + token_id)
    report["token_metadata_http"] = http
    row = doc.get("result") if doc.get("success") is True else None
    if http == 200 and type(row) is dict and row.get("id") == token_id and row.get("enabled") is True:
        try:
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            report["linked_service_token_enabled_unexpired"] = expiry > datetime.now(timezone.utc)
        except (KeyError, TypeError, ValueError):
            pass
    return report


def main() -> int:
    account = os.environ.get("CC_CF_ORIGINAL_ACCOUNT", "").strip()
    if account != ORIGINAL_ACCOUNT:
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
            "finance_access_metadata": inspect_finance_access(account, token),
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
