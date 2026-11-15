"""Obtain one owner-admitted opaque web capsule from existing Cloudflare Fleet.

This public GitHub runner never reads private GitHub sources or credentials.
The only allowed git publication is the validated AES-GCM ciphertext envelope.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from scripts.private_web_capsule_consumer_v1 import capsule_input

AUDIENCE = "mmibkr-fleet-authority"
ENDPOINT = "https://fleet-authority.slenderiq.workers.dev/v1/source-vault/private-web/capsule"
RUN_ID = re.compile(r"\d{4,24}\Z")


def oidc_token() -> str:
    url = str(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL") or "")
    token = str(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN") or "")
    if not url or not token:
        raise RuntimeError("private_web_stage_oidc_missing")
    u = urlparse(url)
    query = dict(parse_qsl(u.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    req = Request(urlunparse((u.scheme, u.netloc, u.path, u.params,
                              urlencode(query), u.fragment)),
                  headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        bearer = str(json.load(response).get("value") or "")
    if bearer.count(".") != 2:
        raise RuntimeError("private_web_stage_oidc_invalid")
    return bearer


def stage(run_id: str, destination: Path, receipt: Path,
          *, token_factory=oidc_token, open_url=urlopen) -> dict:
    if not RUN_ID.fullmatch(str(run_id)):
        raise ValueError("private_web_stage_run_id_rejected")
    bearer = token_factory()
    request = Request(ENDPOINT, data=b"{}", method="POST",
                      headers={"Authorization": "Bearer " + bearer,
                               "X-MMIBKR-Caller-Run-Id": str(run_id),
                               "Content-Type": "application/json",
                               "Accept": "application/json",
                               "User-Agent": "cc-private-web-opaque-stage-v1"})
    try:
        with open_url(request, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError("private_web_stage_not_admitted")
            raw = response.read(1500001)
    except Exception:
        # No Cloudflare/GitHub error bodies or tokens are logged publicly.
        raise RuntimeError("private_web_stage_not_admitted") from None
    capsule, _ = capsule_input(raw)
    if destination.exists() or receipt.exists():
        raise RuntimeError("private_web_stage_destination_exists")
    if destination.name != capsule["capsule_id"] + ".json":
        raise RuntimeError("private_web_stage_destination_id_mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(capsule, sort_keys=True) + "\n",
                           encoding="utf-8")
    result = {
        "schema": "commandcenter.private_web_ciphertext_stage_receipt.v1",
        "state": "CIPHERTEXT_STAGED_NOT_DEPLOYED", "capsule_id": capsule["capsule_id"],
        "ciphertext_sha256": capsule["ciphertext_sha256"],
        "asset_plaintext_published_to_public_git": False,
        "private_source_pin_published_to_public_git": False,
        "oidc_worker_release_admitted": True,
        "cloudflare_hosted_web_access_verified": False,
    }
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--capsule-root", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    # Name is decided by the authenticated Cloudflare response, not the caller.
    # First materialize to an isolated temp file, validate, then publish by id.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="cc-private-web-capsule-") as td:
        response = Path(td) / "capsule.json"
        receipt = Path(td) / "stage-receipt.json"
        # Client receives the capsule id only after the signed Fleet response.
        # Return a temporary pair, then write immutable final names.
        bearer = oidc_token()
        request = Request(ENDPOINT, data=b"{}", method="POST", headers={
            "Authorization": "Bearer " + bearer,
            "X-MMIBKR-Caller-Run-Id": a.run_id,
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "cc-private-web-opaque-stage-v1",
        })
        try:
            with urlopen(request, timeout=60) as res:
                if res.status != 200: raise RuntimeError("private_web_stage_denied")
                raw = res.read(1500001)
        except Exception:
            raise SystemExit("CC_PRIVATE_WEB_SOURCE_STAGE=HELD_NOT_ADMITTED") from None
        capsule, _ = capsule_input(raw)
        dest = a.capsule_root / (capsule["capsule_id"] + ".json")
        if dest.exists() or a.receipt.exists():
            raise SystemExit("CC_PRIVATE_WEB_CAPSULE_DESTINATION_CONFLICT")
        dest.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(capsule, sort_keys=True) + "\n")
        result = {
            "schema":"commandcenter.private_web_ciphertext_stage_receipt.v1",
            "state":"CIPHERTEXT_STAGED_NOT_DEPLOYED",
            "capsule_id":capsule["capsule_id"],
            "ciphertext_sha256":capsule["ciphertext_sha256"],
            "private_source_or_applicant_data_published":False,
            "hosted_deployed":False,
        }
        a.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("CC_PRIVATE_WEB_SOURCE_CAPSULE=ENCRYPTED_STAGED")
        print("CC_PRIVATE_WEB_CAPSULE_ID=" + capsule["capsule_id"])


if __name__ == "__main__":
    main()
