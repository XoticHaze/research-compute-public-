"""Stage only a Cloudflare-sealed private web ciphertext capsule in public Git.

The existing authenticated Fleet owner performs private-source reads and AES
encryption. This public GitHub runner receives NO private source credential,
source SHA, applicant content, or unencrypted release files.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

from scripts.private_web_capsule_consumer_v1 import capsule_input, github_oidc

ENDPOINT = "https://fleet-authority.slenderiq.workers.dev/v1/source-vault/private-web/capsule"
RUN_ID = re.compile(r"\d{4,24}\Z")


def fetch_capsule(run_id: str, *, token_factory=github_oidc, open_url=urlopen) -> dict:
    if not RUN_ID.fullmatch(str(run_id)):
        raise ValueError("private_web_stage_run_id_invalid")
    req = Request(
        ENDPOINT, method="POST", data=b"{}",
        headers={"Authorization": "Bearer " + token_factory(),
                 "X-MMIBKR-Caller-Run-Id": str(run_id),
                 "Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": "cc-private-web-opaque-stage-v1"})
    try:
        with open_url(req, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError("private_web_stage_not_admitted")
            raw = response.read(1_500_001)
    except Exception:
        # Never print Cloudflare error bodies or headers to public Actions.
        raise RuntimeError("private_web_stage_not_admitted") from None
    capsule, _ = capsule_input(raw)
    return capsule


def stage(*, run_id: str, capsule_root: Path, receipt_file: Path,
          token_factory=github_oidc, open_url=urlopen) -> dict:
    capsule = fetch_capsule(run_id, token_factory=token_factory, open_url=open_url)
    destination = capsule_root / (capsule["capsule_id"] + ".json")
    if destination.exists() or receipt_file.exists():
        raise RuntimeError("immutable_web_capsule_destination_conflict")
    capsule_root.mkdir(parents=True, exist_ok=True)
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(capsule, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "schema": "commandcenter.private_web_ciphertext_stage_receipt.v1",
        "state": "CIPHERTEXT_STAGED_NOT_DEPLOYED",
        "capsule_id": capsule["capsule_id"],
        "ciphertext_sha256": capsule["ciphertext_sha256"],
        "applicant_plaintext_published": False,
        "private_source_sha_published": False,
        "hosted_deployed": False,
        "access_served_verified": False,
    }
    receipt_file.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--capsule-root", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    try:
        result = stage(run_id=args.run_id,
                       capsule_root=args.capsule_root,
                       receipt_file=args.receipt)
    except Exception:
        raise SystemExit("CC_PRIVATE_WEB_SOURCE_STAGE=HELD_NOT_ADMITTED") from None
    print("CC_PRIVATE_WEB_SOURCE_CAPSULE=ENCRYPTED_STAGED")
    print("CC_PRIVATE_WEB_CAPSULE_ID=" + result["capsule_id"])


if __name__ == "__main__":
    main()
