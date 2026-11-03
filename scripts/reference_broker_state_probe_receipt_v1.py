"""Sanitized, read-only receipt for the existing neutral reference broker probe.

This observation is NOT independent signer custody or R1 signed admission proof.
No HTTP body, raw public key, token, or untrusted endpoint text reaches output.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import sys

SCHEMA = "reference-broker-state-probe.r1"
MAX_RESPONSE_BYTES = 4096


def _public_key_fingerprint(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    key_id, encoded = value.get("key_id"), value.get("public_b64")
    if not isinstance(key_id, str) or not isinstance(encoded, str):
        return None
    if len(key_id) != 71 or len(encoded) > 128:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None
    # Exact uncompressed P-256 point encoding. On-curve and signature validation
    # remain the private authority's job, not a public readiness observation.
    if len(raw) != 65 or raw[0] != 0x04:
        return None
    if base64.b64encode(raw).decode("ascii") != encoded:
        return None
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return digest if hmac.compare_digest(key_id, digest) else None


def receipt_from_observation(health: object, key: object, health_status: int,
                             key_status: int, run_id: str) -> dict:
    health_ok = (health_status == 200 and isinstance(health, dict)
                 and health.get("ok") is True)
    fingerprint = _public_key_fingerprint(key) if key_status == 200 else None
    key_ok = fingerprint is not None
    if health_ok and key_ok:
        readiness = "HEALTH_AND_KEY_MATCH_NOT_SIGNED_ADMISSION"
    elif health_ok:
        # An older preseal deployment, two active versions, or key export
        # failure can all produce this; HTTP doesn't attest source identity.
        readiness = "HEALTH_ONLY_KEY_UNVERIFIED_SOURCE_UNKNOWN"
    elif key_ok:
        readiness = "KEY_ONLY_HEALTH_UNVERIFIED_SOURCE_UNKNOWN"
    else:
        readiness = "NOT_READY"
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "health_http_status": health_status,
        "health_ok": health_ok,
        "public_key_http_status": key_status,
        "broker_signer_configured": key_ok,
        "broker_key_id": fingerprint,
        "deployed_source_identity_verified": False,
        "independent_signing_admission_verified": False,
        "readiness_observation": readiness,
        "mutation_performed": False,
        "secrets_included": False,
    }


def _read_json(path: str) -> object:
    try:
        with open(path, "rb") as stream:
            payload = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            return {}
        return json.loads(payload)
    except (OSError, ValueError, UnicodeError):
        return {}


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("invalid_probe_arguments")
    health_path, key_path, h_status, k_status = sys.argv[1:]

    def status(text: str) -> int:
        return int(text) if text.isascii() and text.isdecimal() and 0 <= int(text) <= 599 else 0

    receipt = receipt_from_observation(_read_json(health_path), _read_json(key_path),
                                       status(h_status), status(k_status),
                                       os.environ.get("GITHUB_RUN_ID", ""))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
