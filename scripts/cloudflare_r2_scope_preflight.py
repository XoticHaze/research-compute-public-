from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"

def request(token: str, method: str, url: str):
    req = Request(
        url,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "research-cloudflare-r2-preflight",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    try:
        node = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        node = {}
    return status, node

def main() -> int:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise SystemExit("R2 Cloudflare credential missing")

    expected = ["fleet-authority", "mmibkr-operator-console"]
    forbidden = [
        "reference-release-broker-v1",
        "reference-release-maintainer-v1",
        "reference-maintenance-authority-v1",
        "waterboys-fantasy-broker",
    ]

    for worker in expected:
        status, node = request(
            token,
            "GET",
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        if status != 200 or node.get("success") is not True:
            raise SystemExit(f"R2 expected Worker access failed: {worker}:HTTP_{status}")
        print("R2_ALLOW_" + worker.upper().replace("-", "_") + "=1")

    for worker in forbidden:
        status, _ = request(
            token,
            "GET",
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        if status == 200:
            raise SystemExit(f"R2 forbidden Worker reachable: {worker}")
        if status not in {401, 403, 404}:
            raise SystemExit(f"R2 forbidden Worker unexpected status: {worker}:HTTP_{status}")
        print("R2_DENY_" + worker.upper().replace("-", "_") + "=1")

    access_reads = [
        ("ACCESS_ORGANIZATIONS", f"{API}/accounts/{account}/access/organizations"),
        ("ACCESS_POLICIES", f"{API}/accounts/{account}/access/policies?per_page=1"),
        ("ACCESS_APPS", f"{API}/accounts/{account}/access/apps?per_page=1"),
    ]
    for marker, url in access_reads:
        status, node = request(token, "GET", url)
        if status != 200 or node.get("success") is not True:
            raise SystemExit(f"R2 Access read preflight failed: {marker}:HTTP_{status}")
        print("R2_" + marker + "_READ=1")

    print("RESEARCH_CLOUDFLARE_R2_PREFLIGHT_PASS=1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
