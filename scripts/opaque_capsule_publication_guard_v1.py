"""Fail-closed PUBLICATION gate for opaque M1/A1 ciphertext envelopes.

No content/field values, paths, hashes, or user-controlled exceptions are
printed. This is a public metadata guard, not AEAD decryption, trusted-issuer
admission, a hardware-enclave attestation, or historical leak certification.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
from pathlib import Path
import re

from scripts import opaque_bidirectional_capsule_v1 as m1
from scripts import opaque_bidirectional_capsule_p256_aesgcm_v1 as a1

MAX_BYTES = 2_000_000
RUN_ID = re.compile(r"^[0-9]{1,20}$")
KEY_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PROFILES = {m1.SCHEMA: (m1.FIELDS, m1.BUCKETS, "M1"),
            a1.SCHEMA: (a1.FIELDS, a1.BUCKETS, "A1")}

class Rejected(ValueError):
    pass

def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate")
        result[key] = value
    return result

def _b64(value):
    if not isinstance(value, str):
        raise Rejected("type")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise Rejected("base64") from None

def audit_bytes(raw: bytes, *, expected_direction: str) -> bool:
    """Only validated fixed-size AEAD envelope metadata may be published."""
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES or len(raw) < 32:
            raise Rejected("size")
        if expected_direction not in ("request", "result"):
            raise Rejected("expected_direction")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        if not isinstance(data, dict):
            raise Rejected("type")
        spec = PROFILES.get(data.get("schema"))
        if spec is None:
            raise Rejected("schema")
        fields, buckets, profile = spec
        if set(data) != fields:
            raise Rejected("fields")
        if not isinstance(data["run_id"], str) or not RUN_ID.fullmatch(data["run_id"]):
            raise Rejected("run")
        if data["direction"] != expected_direction:
            raise Rejected("direction")
        if not isinstance(data["recipient_key_id"], str) or not KEY_ID.fullmatch(data["recipient_key_id"]):
            raise Rejected("recipient")
        if not isinstance(data["ciphertext_sha256"], str) or not DIGEST.fullmatch(data["ciphertext_sha256"]):
            raise Rejected("digest")
        sender, nonce, ciphertext = (_b64(data[k]) for k in
              ("sender_public_b64", "nonce_b64", "ciphertext_b64"))
        if len(sender) != (32 if profile == "M1" else 33):
            raise Rejected("sender")
        if profile == "A1" and sender[0] not in (2, 3):
            raise Rejected("p256")
        if len(nonce) != 12 or len(ciphertext) not in {b+16 for b in buckets}:
            raise Rejected("padded_length")
        if not hmac.compare_digest(hashlib.sha256(ciphertext).hexdigest(), data["ciphertext_sha256"]):
            raise Rejected("ciphertext_digest")
        return True
    except (Rejected, ValueError, TypeError, UnicodeError):
        return False

def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--direction", choices=("request", "result"), required=True)
    try:
        args = parser.parse_args()
        with args.envelope.open("rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
        accepted = audit_bytes(raw, expected_direction=args.direction)
    except Exception:
        accepted = False
    print("OPAQUE_PUBLICATION_GUARD=" + ("PASS" if accepted else "FAIL_CLOSED"))
    return 0 if accepted else 1

if __name__ == "__main__":
    raise SystemExit(main())
