"""Private-side A1 encrypted terminal validator for the existing reference harness.

This module executes ONLY on an independently authorized private-side
consumer. It reuses the repository's audited P-256/AES-GCM capsule codec and
fixed-field publication guard; no new crypto implementation, key generation,
public compute trigger, Cloudflare credential, or GitHub output is introduced.

A cryptographic H1 result is NOT signed broker admission, an independently
trusted placement issuer, a private grant, or a production route approval.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import open_capsule
from scripts.opaque_capsule_publication_guard_v1 import audit_bytes

RESULT_SCHEMA = "reference-private-result-v1"
RECEIPT_SCHEMA = "reference.private_a1_crypto_terminal.v1"
RUN = re.compile(r"^[1-9][0-9]{0,19}$")
REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
RESULT_OK_FIELDS = frozenset({
    "schema", "request_id", "ok", "output_b64", "cleanup_contract"
})
MAX_PUBLIC_ENVELOPE_BYTES = 2_000_000
MAX_PRIVATE_RESULT_BYTES = 12_288
MAX_EXPECTED_PAYLOAD_BYTES = 1_048_576
CLEANUP = "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT"


class PrivateA1ResultRejected(ValueError):
    """Never embed private inputs, paths, exception messages or ciphertext."""


class _PrivateSafeArgumentParser(argparse.ArgumentParser):
    """Never echo private filenames or unrecognized input on CLI failure."""

    def error(self, _message: str) -> None:
        raise PrivateA1ResultRejected("PRIVATE_A1_ARGS_REJECTED")


def _reject() -> None:
    raise PrivateA1ResultRejected("PRIVATE_A1_RESULT_REJECTED")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    node: dict[str, Any] = {}
    for name, value in pairs:
        if name in node:
            _reject()
        node[name] = value
    return node


def _deny_constant(_: str) -> None:
    _reject()


def accept_reference_h1_result(
    envelope: bytes,
    *,
    return_private_b64: str,
    expected_run_id: str,
    expected_request_id: str,
    expected_request_payload: bytes,
) -> dict[str, Any]:
    """Validate real authenticated result + exact private H1 request identity.

    All exception details are suppressed to prevent public logs from revealing
    hidden request content, cryptographic material or semantic result metadata.
    Receipt is PRIVATE only; no public Job/Issuer/Release authority is granted.
    """
    if (not isinstance(expected_run_id, str) or not RUN.fullmatch(expected_run_id)
        or not isinstance(expected_request_id, str)
        or not REQUEST.fullmatch(expected_request_id)
        or not isinstance(expected_request_payload, bytes)
        or len(expected_request_payload) > MAX_EXPECTED_PAYLOAD_BYTES
        or not isinstance(envelope, bytes)
        or len(envelope) > MAX_PUBLIC_ENVELOPE_BYTES
        or not isinstance(return_private_b64, str)
        or not return_private_b64):
        _reject()
    if not audit_bytes(envelope, expected_direction="result"):
        _reject()
    try:
        envelope_node = json.loads(
            envelope.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_deny_constant
        )
        plaintext = open_capsule(
            envelope_node,
            recipient_private_b64=return_private_b64,
            expected_run_id=expected_run_id,
            expected_direction="result",
        )
        if not isinstance(plaintext, bytes) or not (
            2 <= len(plaintext) <= MAX_PRIVATE_RESULT_BYTES
        ):
            _reject()
        node = json.loads(
            plaintext.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_deny_constant
        )
        if (not isinstance(node, dict) or set(node) != RESULT_OK_FIELDS
            or node.get("schema") != RESULT_SCHEMA
            or node.get("request_id") != expected_request_id
            or node.get("ok") is not True
            or node.get("cleanup_contract") != CLEANUP):
            _reject()
        value = node.get("output_b64")
        if not isinstance(value, str) or len(value) != 44:
            _reject()
        observed = base64.b64decode(value.encode("ascii"), validate=True)
        if len(observed) != 32:
            _reject()
        expected = hashlib.sha256(expected_request_payload).digest()
        if not hmac.compare_digest(observed, expected):
            _reject()
    except Exception:
        _reject()
    return {
        "schema": RECEIPT_SCHEMA,
        "run_id": expected_run_id,
        "request_id": expected_request_id,
        "status": "PRIVATE_A1_H1_CRYPTOGRAPHIC_RESULT_VERIFIED",
        "envelope_authenticated": True,
        "request_content_match": True,
        "release_signature_verified": False,
        "trusted_placement_admitted": False,
        "production_generic_router_admitted": False,
        "result_plaintext_published": False,
    }


def write_private_receipt(receipt: dict[str, Any], path: Path) -> None:
    """Exclusive 0600 private receipt; no overwrite or symlink follow."""
    if (path.is_symlink() or path.exists() or path.parent.is_symlink()
        or not path.parent.is_dir()):
        _reject()
    raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(raw) > 2048:
        _reject()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        _reject()


def main() -> int:
    parser = _PrivateSafeArgumentParser(add_help=False)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--request-payload", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--private-receipt", type=Path, required=True)
    try:
        args = parser.parse_args()
        private_key = os.environ.pop("REFERENCE_PRIVATE_A1_RETURN_KEY_B64", "")
        if not private_key:
            _reject()
        envelope = args.envelope.read_bytes()
        payload = args.request_payload.read_bytes()
        receipt = accept_reference_h1_result(
            envelope, return_private_b64=private_key,
            expected_run_id=args.run_id,
            expected_request_id=args.request_id,
            expected_request_payload=payload,
        )
        write_private_receipt(receipt, args.private_receipt)
    except BaseException:
        # Constant output. No exception message, source path or private metadata.
        sys.stdout.write("REFERENCE_PRIVATE_A1_TERMINAL=FAIL_CLOSED\n")
        return 1
    sys.stdout.write("REFERENCE_PRIVATE_A1_TERMINAL=CRYPTO_VERIFIED_ONLY\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
