from __future__ import annotations

import json
import os
from pathlib import Path
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

    # Fleet deployments must survive removal of console privileges from R2.
    # Default "dual" preserves existing callers before the protected cutover.
    profile = os.environ.get("CLOUDFLARE_R2_SCOPE_PROFILE", "dual").strip()
    if profile not in {"dual", "fleet_transition", "fleet_strict"}:
        raise SystemExit("R2 scope profile invalid")
    expected = ["fleet-authority", "mmibkr-operator-console"] if profile == "dual" else ["fleet-authority"]
    forbidden = [
        "reference-release-broker-v1",
        "reference-release-maintainer-v1",
        "reference-maintenance-authority-v1",
        "waterboys-fantasy-broker",
    ]

    if profile == "fleet_strict":
        forbidden.append("mmibkr-operator-console")

    matrix: dict[str, int] = {}
    failure = ""

    for worker in expected:
        status, node = request(
            token,
            "GET",
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        matrix[worker] = status
        if not failure and (status != 200 or node.get("success") is not True):
            failure = f"expected_worker_denied:{worker}:HTTP_{status}"

    for worker in forbidden:
        status, _ = request(
            token,
            "GET",
            f"{API}/accounts/{account}/workers/scripts/{worker}/settings",
        )
        matrix[worker] = status
        if not failure and status == 200:
            failure = f"forbidden_worker_reachable:{worker}"
        elif not failure and status not in {401, 403, 404}:
            failure = f"forbidden_worker_unexpected:{worker}:HTTP_{status}"

    if profile == "fleet_transition":
        # This is a read-only observation, not an Editor-denial proof.
        status, node = request(
            token,
            "GET",
            f"{API}/accounts/{account}/workers/scripts/mmibkr-operator-console/settings",
        )
        matrix["mmibkr-operator-console"] = status
        if not failure and (status not in {200, 401, 403, 404}
                            or (status == 200 and node.get("success") is not True)):
            failure = f"operator_console_read_unexpected:HTTP_{status}"

    receipt = {
        "schema": "research.cloudflare_r2_scope_preflight.r1",
        "scope_profile": profile,
        "worker_settings_http": matrix,
        "expected_allow": expected,
        "expected_deny": forbidden,
        "pass": not bool(failure),
        "failure": failure,
        "mutation_performed": False,
        "secret_included": False,
    }
    out = Path("rendezvous/receipts/research-cloudflare-r2-scope-preflight.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for worker in expected:
        if matrix.get(worker) == 200:
            print("R2_ALLOW_" + worker.upper().replace("-", "_") + "=1")
    for worker in forbidden:
        if matrix.get(worker) in {401, 403, 404}:
            print("R2_DENY_" + worker.upper().replace("-", "_") + "=1")

    if failure:
        raise SystemExit("RESEARCH_CLOUDFLARE_R2_PREFLIGHT_REJECTED=" + failure)

    print("RESEARCH_CLOUDFLARE_R2_PREFLIGHT_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
