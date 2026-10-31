#!/usr/bin/env python3
"""Read-only authentication of the exact historical MM-IBKR runtime checkpoint.

No broker, Docker, Gateway, device, credential handoff, or runtime restore.
The original AES-GCM master stays in the existing public-workflow secret
context and is never printed or written to an output artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from scripts.mmibkr_live_gateway_state_envelope_v1 import read_master
from scripts.mmibkr_live_runtime_checkpoint_v1 import unseal
from scripts.mmibkr_original_checkpoint_botdata_capsule_v1 import seal_quarantine, write_capsule

SCHEMA = "mmibkr.original_live_checkpoint_readonly_review.v1"
RUN_ID = "39499524894"
EXPECTED_CONTEXT_SOURCE = "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b"
EXPECTED_CIPHER_BYTES = 33560349
EXPECTED_CIPHER_SHA256 = "7fa732e25dbb9044ba66c8fb9e3f7da4e269434ee7b2708d635f58c7d914bc66"
EXPECTED_MANIFEST_BYTES_MAX = 8192
EXPECTED_SELECTED_SOURCE = "45339615b1a8b27a5e34233f9cb849c0ae6ecab8"
def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_bounded_regular_file(path: Path, limit: int) -> bytes:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size <= 0 or st.st_size > limit:
        raise ValueError("input_file_size_or_type_invalid")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) != st.st_size:
        raise ValueError("input_file_size_changed")
    return data


def _validate_exact_context(meta: dict) -> None:
    if not isinstance(meta, dict) or not isinstance(meta.get("context"), dict):
        raise ValueError("historical_manifest_invalid")
    ctx = meta["context"]
    if ctx.get("run_id") != RUN_ID or ctx.get("source_sha") != EXPECTED_CONTEXT_SOURCE:
        raise ValueError("historical_producer_identity_mismatch")
    if ctx.get("scope") != ["AMAT", "APH", "MNQ"]:
        raise ValueError("historical_selected_scope_mismatch")
    if ctx.get("order_authority") != "none_checkpoint_requires_fresh_canonical_admission":
        raise ValueError("historical_order_authority_invalid")
    if meta.get("ciphertext_sha256") != EXPECTED_CIPHER_SHA256:
        raise ValueError("historical_ciphertext_digest_invalid")
    if meta.get("ciphertext_bytes") != EXPECTED_CIPHER_BYTES:
        raise ValueError("historical_ciphertext_size_invalid")


def classify_authenticated_archive(raw: bytes, successor_run_id: str) -> dict:
    return {
        "schema": SCHEMA,
        "historical_producer_run": RUN_ID,
        "historical_producer_source_sha": EXPECTED_CONTEXT_SOURCE,
        "selected_pi_source_sha": EXPECTED_SELECTED_SOURCE,
        "consumer_run_id": successor_run_id,
        "authenticated_aes_gcm": True,
        "historical_gateway_tree_must_not_be_restored": True,
        "historical_live_policy_cannot_be_imported_directly": True,
        "postincident_broker_history_reconciliation_required": True,
        "protected_root_migration_approval_required": True,
        "no_submit_bot_start_allowed": False,
        "live_order_submit_allowed": False,
        "decrypted_plaintext_artifact_published": False,
        "master_key_emitted": False,
        "gateway_started": False,
        "broker_contacted": False,
        "pi_modified": False,
    }


def _authenticate_report_and_raw(envelope: bytes, manifest: bytes, key: bytes, successor_run_id: str) -> tuple[dict, bytes]:
    if _sha(envelope) != EXPECTED_CIPHER_SHA256 or len(envelope) != EXPECTED_CIPHER_BYTES:
        raise ValueError("historical_ciphertext_identity_invalid")
    if len(manifest) > EXPECTED_MANIFEST_BYTES_MAX:
        raise ValueError("historical_manifest_size_invalid")
    meta = json.loads(manifest)
    _validate_exact_context(meta)
    if not re.fullmatch(r"[0-9]{4,24}", successor_run_id) or successor_run_id == RUN_ID:
        raise ValueError("current_consumer_run_identity_invalid")
    raw = unseal(envelope, meta, successor_run_id, key)
    return classify_authenticated_archive(raw, successor_run_id), raw


def inspect_exact(envelope: bytes, manifest: bytes, key: bytes, successor_run_id: str) -> dict:
    return _authenticate_report_and_raw(envelope, manifest, key, successor_run_id)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciphertext", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--consumer-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipient-public-b64")
    parser.add_argument("--approved-recipient-key-id")
    parser.add_argument("--capsule-dir", type=Path)
    parser.add_argument("--authenticate-only", action="store_true")
    args = parser.parse_args()
    try:
        # Secret is read from the *existing* approved public workflow environment.
        key = read_master()
        blob = _read_bounded_regular_file(args.ciphertext, EXPECTED_CIPHER_BYTES)
        manifest = _read_bounded_regular_file(args.manifest, EXPECTED_MANIFEST_BYTES_MAX)
        result, authenticated_plaintext = _authenticate_report_and_raw(blob, manifest, key, args.consumer_run_id)
        if args.authenticate_only:
            if args.capsule_dir is not None or args.recipient_public_b64 or args.approved_recipient_key_id:
                raise ValueError('authenticate_only_refuses_any_return_recipient')
            result["recipient_botdata_quarantine_ciphertext_created"] = False
        else:
            if not (args.capsule_dir and args.recipient_public_b64 and args.approved_recipient_key_id):
                raise ValueError('quarantine_requires_explicit_approved_recipient_and_directory')
            ciphertext, envelope = seal_quarantine(authenticated_plaintext, args.recipient_public_b64, args.consumer_run_id, args.approved_recipient_key_id)
            write_capsule(args.capsule_dir, ciphertext, envelope)
            result["recipient_botdata_quarantine_ciphertext_created"] = True
        # Sanitized allowlist only, exclusive creation; never write raw/key.
        fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(result, fp, sort_keys=True, separators=(",", ":"))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        print("MMIBKR_ORIGINAL_CHECKPOINT_AES_GCM=PASS")
        if args.authenticate_only:
            print("MMIBKR_ORIGINAL_CHECKPOINT_RETURN=NONE_AUTHENTICATION_ONLY")
        else:
            print("MMIBKR_ORIGINAL_CHECKPOINT_RECIPIENT_BOTDATA_CAPSULE=SEALED_QUARANTINE_ONLY")
        print("MMIBKR_NO_SUBMIT_OR_LIVE_ADMISSION=HELD")
        return 0
    except Exception as exc:
        # Do not expose any exception details in public logs: sensitive inputs
        # can leak through lower-layer HTTP/crypto/JSON exceptions.
        print("MMIBKR_ORIGINAL_CHECKPOINT_REVIEW=FAIL_CLOSED:" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
