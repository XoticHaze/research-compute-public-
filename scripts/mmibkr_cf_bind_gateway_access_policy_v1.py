"""Bind an existing Cloudflare Access service token to one exact SSH Gateway app.

Operational fail-closed contract:
- Only the operator-selected Shared Compute account, exact active zone and hostname.
- Never create or log credentials, tokens, client secrets, tunnel tokens, or IDs.
- Do not attach Allow/Bypass/Everyone/Any-valid-service-token policies.
- Never change DNS, tunnels, Workers, broker sessions or schedules.
"""
from __future__ import annotations

import os
from urllib.parse import urlencode
from scripts.mmibkr_cf_access_existing_token_probe_v1 import (
    APP_NAME, DOMAIN, HOST, ScopedAPI,
)

TOKEN_NAME = "mmibkr-github-readers"
POLICY_NAME = "mmibkr-github-service-only"


def is_hex_id(value: object) -> bool:
    """Accept Cloudflare's 32-hex or canonical UUID resource identifiers."""
    if not isinstance(value, str):
        return False
    compact = value.replace("-", "")
    if not (len(compact) == 32 and all(c in "0123456789abcdefABCDEF" for c in compact)):
        return False
    return len(value) == 32 or (len(value) == 36 and
                                [i for i, c in enumerate(value) if c == "-"] == [8, 13, 18, 23])


def approved_policy(policy: object, token_id: str) -> bool:
    if not isinstance(policy, dict):
        return False
    if policy.get("name") != POLICY_NAME or policy.get("decision") != "non_identity":
        return False
    inc = policy.get("include")
    return (
        isinstance(inc, list)
        and len(inc) == 1
        and isinstance(inc[0], dict)
        and inc[0] == {"service_token": {"token_id": token_id}}
        and not policy.get("require")
        and not policy.get("exclude")
    )


def provision(api: ScopedAPI, client_id: str, *, service_secret_present: bool) -> str:
    account = api.account
    if not client_id or not service_secret_present:
        return "BLOCKED_READER_SERVICE_TOKEN_SECRETS_MISSING"
    ok, code, zones = api.call("GET", "/zones?" + urlencode({"name": DOMAIN, "per_page": 50}))
    if not ok or not isinstance(zones, list):
        return "BLOCKED_EXACT_ZONE_READ_HTTP_" + str(code)
    if len([
        z for z in zones if isinstance(z, dict)
        and z.get("name") == DOMAIN and z.get("status") == "active"
        and isinstance(z.get("account"), dict) and z["account"].get("id") == account
    ]) != 1:
        return "BLOCKED_ACTIVE_ZONE_ACCOUNT_MISMATCH"

    ok, code, tokens = api.call("GET", f"/accounts/{account}/access/service_tokens?per_page=100")
    if not ok or not isinstance(tokens, list):
        return "BLOCKED_SERVICE_TOKEN_READ_HTTP_" + str(code)
    matching_tokens = [t for t in tokens if isinstance(t, dict)
                       and t.get("client_id") == client_id
                       and t.get("name") == TOKEN_NAME
                       and is_hex_id(t.get("id"))
                       and t.get("enabled") is not False]
    if len(matching_tokens) != 1:
        return "BLOCKED_EXPECTED_NAMED_SERVICE_TOKEN_NOT_FOUND"
    token_id = matching_tokens[0]["id"]

    ok, code, apps = api.call("GET", f"/accounts/{account}/access/apps?per_page=100")
    if not ok or not isinstance(apps, list):
        return "BLOCKED_APP_READ_HTTP_" + str(code)
    matched = [
        x for x in apps if isinstance(x, dict) and
        (x.get("domain") == HOST or x.get("name") == APP_NAME)
    ]
    if len(matched) != 1:
        return "BLOCKED_UNIQUE_GATEWAY_APP_NOT_FOUND"
    app = matched[0]
    if (app.get("domain"), app.get("name"), app.get("type")) != (HOST, APP_NAME, "self_hosted"):
        return "BLOCKED_GATEWAY_APP_IDENTITY_COLLISION"
    if not is_hex_id(app.get("id")):
        return "BLOCKED_GATEWAY_APP_ID_INVALID"
    app_id = app["id"]

    ok, code, policies = api.call("GET", f"/accounts/{account}/access/policies?per_page=100")
    if not ok or not isinstance(policies, list):
        return "BLOCKED_POLICIES_READ_HTTP_" + str(code)
    named = [x for x in policies if isinstance(x, dict) and x.get("name") == POLICY_NAME]
    if len(named) > 1:
        return "BLOCKED_DUPLICATE_POLICY_NAME"
    if named:
        policy = named[0]
        if not approved_policy(policy, token_id) or not is_hex_id(policy.get("id")):
            return "BLOCKED_EXISTING_POLICY_DOES_NOT_MATCH_TOKEN"
        policy_id = policy["id"]
    else:
        policy_body = {
            "name": POLICY_NAME,
            "decision": "non_identity",  # Cloudflare UI: Service Auth
            "include": [{"service_token": {"token_id": token_id}}],
            "require": [],
            "exclude": [],
        }
        ok, code, policy = api.call("POST", f"/accounts/{account}/access/policies", policy_body)
        if not ok:
            return "BLOCKED_POLICY_CREATE_HTTP_" + str(code)
        if not approved_policy(policy, token_id) or not is_hex_id(policy.get("id")):
            return "BLOCKED_CREATED_POLICY_UNVERIFIED"
        policy_id = policy["id"]
        print("MMIBKR_CF_SERVICE_AUTH_POLICY_CREATED=PASS")

    # Only mutate the app when the current policy set is empty (previously
    # deny-default) or already consists exactly of the intended reusable policy.
    app_policies = app.get("policies")
    if not isinstance(app_policies, list):
        return "BLOCKED_GATEWAY_APP_POLICIES_NOT_READABLE"
    existing_ids = [p.get("id") if isinstance(p, dict) else p for p in app_policies]
    if existing_ids not in ([], [policy_id]):
        return "BLOCKED_EXISTING_APP_POLICIES_NOT_EXCLUSIVE"
    if existing_ids == []:
        update = {
            "name": APP_NAME, "domain": HOST, "type": "self_hosted",
            "session_duration": "1h", "app_launcher_visible": False,
            "service_auth_401_redirect": True,
            "policies": [{"id": policy_id, "account_id": account, "precedence": 1}],
        }
        ok, code, _ = api.call("PUT", f"/accounts/{account}/access/apps/{app_id}", update)
        if not ok:
            return "BLOCKED_EXACT_APP_POLICY_BIND_HTTP_" + str(code)
        print("MMIBKR_CF_GATEWAY_POLICY_BIND_WRITE=PASS")
    else:
        print("MMIBKR_CF_GATEWAY_POLICY_BIND_ALREADY_PRESENT=PASS")

    # Independent read-back. Do not declare success just because PUT returned 200.
    ok, code, after = api.call("GET", f"/accounts/{account}/access/apps/{app_id}")
    if not ok or not isinstance(after, dict):
        return "BLOCKED_APP_READBACK_HTTP_" + str(code)
    if (after.get("domain"), after.get("name"), after.get("type")) != (HOST, APP_NAME, "self_hosted"):
        return "BLOCKED_APP_READBACK_IDENTITY"
    linked = after.get("policies")
    if not isinstance(linked, list) or len(linked) != 1:
        return "BLOCKED_APP_READBACK_POLICY_COUNT"
    linked_id = linked[0].get("id") if isinstance(linked[0], dict) else linked[0]
    if linked_id != policy_id:
        return "BLOCKED_APP_READBACK_WRONG_POLICY"
    ok, code, after_policy = api.call("GET", f"/accounts/{account}/access/policies/{policy_id}")
    if not ok or not approved_policy(after_policy, token_id):
        return "BLOCKED_POLICY_READBACK_WRONG_AUTHORITY"
    return "PASS_EXACT_SERVICE_AUTH_ONLY"


def main() -> int:
    token = os.environ.get("CLOUDFLARE_GATEWAY_ACCESS_TOKEN", "").strip()
    account = os.environ.get("CLOUDFLARE_GATEWAY_ACCOUNT_ID", "").strip()
    client_id = os.environ.get("MMIBKR_CF_ACCESS_SERVICE_TOKEN_ID", "").strip()
    client_secret = os.environ.get("MMIBKR_CF_ACCESS_SERVICE_TOKEN_SECRET", "")
    if not token or not is_hex_id(account):
        print("MMIBKR_CF_GATEWAY_SERVICE_AUTH=BLOCKED_SHARED_COMPUTE_CREDENTIALS_MISSING")
        return 41
    result = provision(ScopedAPI(token, account), client_id,
                       service_secret_present=bool(client_secret))
    print("MMIBKR_CF_GATEWAY_SERVICE_AUTH=" + result)
    print("MMIBKR_CF_BROKER_SESSION_STARTED=NO")
    print("MMIBKR_CF_DNS_OR_BILLING_MUTATED=NO")
    return 0 if result == "PASS_EXACT_SERVICE_AUTH_ONLY" else 42


if __name__ == "__main__":
    raise SystemExit(main())
