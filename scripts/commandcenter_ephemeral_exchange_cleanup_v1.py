from __future__ import annotations

"""Remove this completed run's public rendezvous tip files, not Git history.

The public producer/worker already exchanged the input before this cleanup
step runs. Deleting only the exact run-scoped recipient and input envelope
reduces lingering public metadata and ciphertext. It is NOT cryptographic
erasure, Git-history rewriting, or a replacement for an opaque v2 envelope.
"""

import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPOSITORY = "XoticHaze/research-compute-public-"
BRANCH = "rendezvous-exchange"
PROOF_KINDS = {
    "neutral_gate": "commandcenter-neutral-gate-envelope.json",
    "ledger": "commandcenter-ledger-envelope.json",
}
SHA40 = re.compile(r"^[a-f0-9]{40}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")


def paths_for(run_id: str, proof_kind: str) -> tuple[str, str]:
    if not RUN_ID.fullmatch(str(run_id)):
        raise ValueError("run_identity_rejected")
    if proof_kind not in PROOF_KINDS:
        raise ValueError("proof_kind_rejected")
    return (
        f"rendezvous/responses/{run_id}/{PROOF_KINDS[proof_kind]}",
        f"rendezvous/recipients/{run_id}.json",
    )


def _api(method: str, path: str, token: str, data: dict | None = None) -> dict:
    if not token:
        raise RuntimeError("token_missing")
    url = f"https://api.github.com/repos/{REPOSITORY}/contents/{path}"
    if method == "GET":
        url += "?ref=" + BRANCH
    payload = None if data is None else json.dumps(data, separators=(",", ":")).encode()
    req = Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "commandcenter-ephemeral-cleanup-v1",
        },
    )
    with urlopen(req, timeout=20) as response:
        return json.load(response)


def cleanup(*, repo: str, run_id: str, proof_kind: str, token: str, api=_api) -> dict:
    if repo != REPOSITORY:
        raise ValueError("repository_identity_rejected")
    if not token:
        raise ValueError("cleanup_token_missing")
    paths = paths_for(run_id, proof_kind)
    deleted = 0
    absent = 0
    for path in paths:
        for attempt in range(3):
            try:
                result = api("GET", path, token)
            except HTTPError as exc:
                if exc.code == 404:
                    absent += 1
                    break
                raise RuntimeError("exchange_lookup_rejected") from None
            if not isinstance(result, dict) or not SHA40.fullmatch(str(result.get("sha") or "")):
                raise RuntimeError("exchange_file_identity_rejected")
            try:
                api("DELETE", path, token, {
                    "message": "privacy: retire consumed one-run encrypted exchange inputs",
                    "sha": result["sha"],
                    "branch": BRANCH,
                })
                deleted += 1
                break
            except HTTPError as exc:
                if exc.code in (409, 422) and attempt < 2:
                    continue
                if exc.code == 404:
                    # A concurrent authorized cleanup has already retired it.
                    absent += 1
                    break
                raise RuntimeError("exchange_retirement_rejected") from None
        else:
            raise RuntimeError("exchange_retirement_retries_exhausted")
    return {"status": "PASS", "removed_current_tip": deleted, "already_absent": absent}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--proof-kind", required=True)
    args = parser.parse_args()
    try:
        summary = cleanup(
            repo=os.environ.get("GITHUB_REPOSITORY", ""),
            run_id=args.run_id,
            proof_kind=args.proof_kind,
            token=os.environ.get("GH_TOKEN", ""),
        )
    except Exception:
        # Keep HTTP/API bodies, paths, headers and token out of public logs.
        print("COMMANDCENTER_EPHEMERAL_RETENTION=FAIL_CLOSED")
        return 1
    print("COMMANDCENTER_EPHEMERAL_RETENTION=" + summary["status"])
    print("COMMANDCENTER_EPHEMERAL_RETENTION_REMOVED=" + str(summary["removed_current_tip"]))
    print("COMMANDCENTER_EPHEMERAL_RETENTION_ALREADY_ABSENT=" + str(summary["already_absent"]))
    print("COMMANDCENTER_EPHEMERAL_RETENTION_HISTORY_PURGED=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
