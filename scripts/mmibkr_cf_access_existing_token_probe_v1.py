from __future__ import annotations

"""Read existing GitHub-stored Cloudflare token scopes, optionally protect
the specific approved Gateway SSH hostname with a deny-by-default Access app.

Never reads, creates, logs, or transfers a Cloudflare service-token secret.
Never mutates Worker applications, DNS, Tunnel routes, or IBKR.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DOMAIN = "lifelatelycounseling.com"
HOST = "gateway-ops." + DOMAIN
APP_NAME = "MM-IBKR GitHub Gateway SSH"
ALLOWED_INCUMBENT = {
    "mmibkr-operator-console.slenderiq.workers.dev",
    "MM-IBKR Operator Console",
}
BASE = "https://api.cloudflare.com/client/v4"


class ScopedAPI:
    def __init__(self, token: str, account: str, *, opener=urlopen):
        self._token = token
        self.account = account
        self._opener = opener

    def call(self, method: str, path: str, data: dict | None = None):
        body = json.dumps(data).encode() if data is not None else None
        req = Request(BASE + path, data=body, method=method, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "mmibkr-gateway-access-scope-r1",
        })
        try:
            with self._opener(req, timeout=20) as resp:
                status = getattr(resp, "status", 200)
                response = json.load(resp)
        except HTTPError as exc:
            # Never include response body, headers, names, secrets or IDs.
            return False, int(exc.code), None
        except (URLError, ValueError, TimeoutError, OSError):
            return False, 0, None
        if not isinstance(response, dict) or response.get("success") is not True:
            return False, int(status), None
        return True, int(status), response.get("result")


def summarize_token(token: str, account: str, name: str, *, opener=urlopen):
    if not token:
        print("MMIBKR_CF_" + name + "_TOKEN=MISSING")
        return None
    api = ScopedAPI(token, account, opener=opener)
    for label, path in [
        ("ACCESS_APPS_READ", f"/accounts/{account}/access/apps?per_page=100"),
        ("SERVICE_TOKENS_READ", f"/accounts/{account}/access/service_tokens?per_page=100"),
        ("DOMAIN_ZONE_READ", "/zones?" + urlencode({"name": DOMAIN, "per_page": 50})),
    ]:
        ok, status, data = api.call("GET", path)
        print(f"MMIBKR_CF_{name}_{label}={'PASS' if ok else 'HTTP_' + str(status)}")
        if label == "ACCESS_APPS_READ":
            api.apps = data if ok and isinstance(data, list) else None
        elif label == "SERVICE_TOKENS_READ":
            api.tokens = data if ok and isinstance(data, list) else None
        elif label == "DOMAIN_ZONE_READ":
            api.zones = data if ok and isinstance(data, list) else None
    return api


def protect_gateway_deny_default(api: ScopedAPI, *, approved: bool) -> str:
    if not approved:
        return "NOT_REQUESTED"
    # Account-specific API path already binds the existing authorized credential.
    # Do not require unrelated zone-read or incumbent app-read scopes to attempt
    # an exact one-app POST. A 403/400 is a useful, safe server-side result.
    apps = api.apps if isinstance(getattr(api, "apps", None), list) else []
    collisions = [x for x in apps if isinstance(x, dict)
                  and (x.get("domain") == HOST or x.get("name") == APP_NAME)]
    if len(collisions) > 1:
        return "BLOCKED_DUPLICATE_APPLICATION_COLLISION"
    if collisions:
        item = collisions[0]
        if item.get("domain") != HOST or item.get("name") != APP_NAME:
            return "BLOCKED_NONMATCHING_EXISTING_APPLICATION"
        return "EXISTS_PRESERVED_NO_MUTATION"
    body = {
        "name": APP_NAME,
        "domain": HOST,
        "type": "self_hosted",
        "session_duration": "1h",
        "app_launcher_visible": False,
        # Deliberately no Allow, Bypass or Service Auth until operator
        # binds a dedicated identity; default denied to all.
        "policies": [],
    }
    ok, status, result = api.call("POST", f"/accounts/{api.account}/access/apps", body)
    if not ok:
        return "POST_REJECTED_HTTP_" + str(status)
    if not isinstance(result, dict) or result.get("domain") != HOST:
        return "POST_RESPONSE_UNVERIFIED"
    return "CREATED_DENY_DEFAULT_NO_SERVICE_TOKEN"


def main() -> int:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not (len(account) == 32 and all(c in "0123456789abcdefABCDEF" for c in account)):
        print("MMIBKR_CF_ACCOUNT_ID_CONFIGURED=NO")
        return 0
    print("MMIBKR_CF_ACCOUNT_ID_CONFIGURED=YES")
    legacy = summarize_token(os.getenv("CLOUDFLARE_LEGACY_TOKEN", ""), account, "LEGACY")
    summarize_token(os.getenv("CLOUDFLARE_R2_TOKEN", ""), account, "R2")
    if legacy:
        status = protect_gateway_deny_default(
            legacy,
            approved=os.getenv("MMIBKR_CF_ACCESS_CREATE_DENY_DEFAULT") == "1",
        )
        print("MMIBKR_CF_GATEWAY_ACCESS_RECONCILE=" + status)
    else:
        print("MMIBKR_CF_GATEWAY_ACCESS_RECONCILE=BLOCKED_LEGACY_TOKEN_MISSING")
    print("MMIBKR_CF_SERVICE_TOKEN_CREATE_ATTEMPTED=NO")
    print("MMIBKR_CF_BROKER_AUTH_ATTEMPTED=NO")
    print("MMIBKR_CF_DNS_MUTATION_ATTEMPTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
