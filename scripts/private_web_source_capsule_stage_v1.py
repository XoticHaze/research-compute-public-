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
from urllib.error import HTTPError

from scripts.private_web_capsule_consumer_v1 import capsule_input, github_oidc

ENDPOINT = "https://fleet-authority.slenderiq.workers.dev/v1/source-vault/private-web/capsule"
RUN_ID = re.compile(r"\d{4,24}\Z")
SAFE_HELD = frozenset({
    'private_web_source_stage_owner_approval_missing',
    'private_web_owner_source_token_unavailable',
    'private_web_owner_source_read_denied',
    'private_web_owner_release_authority_not_admitted',
    'private_web_owner_release_manifest_rejected',
    'private_web_owner_asset_spec_mismatch',
    'private_web_owner_source_digest_mismatch',
    'private_web_inline_script_rejected',
    'private_web_inline_event_handler_rejected',
    'private_web_source_key_not_verified',
    'private_web_source_unclassified_denial',
})


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
    except HTTPError as exc:
        # Fixed finite error categories only. Do not echo provider status bodies.
        try:
            node = json.loads(exc.read(512))
            reason = node.get('held_reason') if isinstance(node, dict) else None
            if (node.get('error') != 'private_web_source_seal_not_admitted'
                    or reason not in SAFE_HELD):
                reason = 'private_web_source_unclassified_denial'
        except Exception:
            reason = 'private_web_source_unclassified_denial'
        raise RuntimeError('private_web_source_held:' + reason) from None
    except Exception:
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
    except RuntimeError as error:
        message = str(error)
        if message.startswith('private_web_source_held:'):
            reason = message.split(':', 1)[1]
            if reason in SAFE_HELD:
                print('CC_PRIVATE_WEB_SOURCE_STAGE_HELD_REASON=' + reason)
        raise SystemExit("CC_PRIVATE_WEB_SOURCE_STAGE=HELD_NOT_ADMITTED") from None
    except Exception:
        raise SystemExit("CC_PRIVATE_WEB_SOURCE_STAGE=HELD_NOT_ADMITTED") from None
    print("CC_PRIVATE_WEB_SOURCE_CAPSULE=ENCRYPTED_STAGED")
    print("CC_PRIVATE_WEB_CAPSULE_ID=" + result["capsule_id"])


if __name__ == "__main__":
    main()
