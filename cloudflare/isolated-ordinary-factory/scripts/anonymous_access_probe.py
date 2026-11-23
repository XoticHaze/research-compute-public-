#!/usr/bin/env python3
"""Fixed-target anonymous GET-only Access challenge test; no credentials, cookies, URLs in output."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TARGET = ("https://cc-ordinary-worker-factory."
          "cc-ordinary-deployments.workers.dev/v1/status")
SCHEMA = "commandcenter.cloudflare.factory_status.v1"


def classify(status, redirect_url="", content_type="", body=b""):
    """Return safe, bounded classification. Never return body or redirect URL."""
    snippet = body[:3000].decode("utf-8", "ignore") if isinstance(body, bytes) else ""
    if SCHEMA in snippet:
        return "FAIL_OWNER_STATUS_ANONYMOUSLY_REACHABLE"
    if status in (301, 302, 303, 307, 308) and redirect_url:
        parsed = urllib.parse.urlsplit(redirect_url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        if parsed.scheme == "https" and (
                path.startswith("/cdn-cgi/access/") and (
                    host.endswith(".cloudflareaccess.com") or
                    host == "cc-ordinary-worker-factory.cc-ordinary-deployments.workers.dev")):
            return "ACCESS_LOGIN_REDIRECT_VERIFIED"
        return "REDIRECT_UNCLASSIFIED"
    if status in (401, 403):
        if "cloudflare access" in snippet.lower() or (
                "/cdn-cgi/access/" in snippet.lower()):
            return "ACCESS_DENIAL_PAGE_VERIFIED"
        return "DENIAL_UNCLASSIFIED"
    return "UNVERIFIED"


def probe():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    req = urllib.request.Request(TARGET, headers={
        "Accept": "application/json",
        "User-Agent": "cc-factory-anonymous-edge-audit-v1",
    }, method="GET")
    client = urllib.request.build_opener(NoRedirect())
    try:
        with client.open(req, timeout=15) as response:
            return response.status, response.headers.get("Location", ""), (
                response.headers.get("Content-Type", "")), response.read(3000)
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Location", ""), (
            err.headers.get("Content-Type", "")), err.read(3000)


def main():
    try:
        status, location, content_type, body = probe()
        result = classify(status, location, content_type, body)
    except (TimeoutError, urllib.error.URLError, OSError, ValueError):
        status, result = None, "NETWORK_UNVERIFIED"
    receipt = {
        "schema": "commandcenter.cloudflare.factory.anonymous_access_probe.v1",
        "account_role": "CC_ISOLATED_ORDINARY_ONLY",
        "worker": "cc-ordinary-worker-factory",
        "observation_time_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": status,
        "classification": result,
        "cloudflare_mutations": 0,
        "credentials_sent": False,
        "cookies_sent": False,
        "identity_returned": False,
        "no_mac_required": True,
    }
    print(json.dumps(receipt, sort_keys=True))
    # Access gate specifically identified; unclassified denial is not approval.
    return 0 if result in ("ACCESS_LOGIN_REDIRECT_VERIFIED",
                           "ACCESS_DENIAL_PAGE_VERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
