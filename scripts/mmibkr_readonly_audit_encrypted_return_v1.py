from __future__ import annotations

"""Encrypt one read-only MM-IBKR audit JSON to a one-time X25519 recipient."""

import argparse
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

REQUEST_SCHEMA = "mmibkr.readonly_audit_return_request.v1"
AUDIT_SCHEMA = "mmibkr.selected_runtime_missed_trade_audit.v1"
ENVELOPE_SCHEMA = "mmibkr.readonly_audit_encrypted_return_x25519.v1"
INFO = b"mmibkr-readonly-audit-encrypted-return-v1"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: str | Path) -> dict[str, Any]:
    node = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("json_object_required")
    return node


def validate_request(node: Mapping[str, Any]) -> tuple[str, bytes, str]:
    if node.get("return_schema") != REQUEST_SCHEMA:
        raise RuntimeError("readonly_audit_return_request_schema_rejected")
    request_id = str(node.get("request_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,96}", request_id):
        raise RuntimeError("readonly_audit_return_request_id_rejected")
    recipient_b64 = str(node.get("recipient_b64") or "").strip()
    recipient_key_id = str(node.get("recipient_key_id") or "").strip()
    try:
        recipient_raw = base64.b64decode(recipient_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("readonly_audit_recipient_key_invalid_base64") from exc
    if len(recipient_raw) != 32:
        raise RuntimeError("readonly_audit_recipient_key_must_be_32_bytes")
    expected = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if recipient_key_id != expected:
        raise RuntimeError("readonly_audit_recipient_fingerprint_mismatch")
    return request_id, recipient_raw, recipient_key_id


def validate_audit(node: Mapping[str, Any]) -> None:
    if node.get("schema") != AUDIT_SCHEMA or node.get("ok") is not True:
        raise RuntimeError("readonly_audit_payload_rejected")
    safety = node.get("safety") if isinstance(node.get("safety"), Mapping) else {}
    required_false = (
        "broker_action",
        "broker_request_made",
        "paper_submit_invoked",
        "cancel_invoked",
        "flatten_invoked",
        "strategy_spec_mutation",
        "runtime_authority_mutation",
        "account_positions_promoted_to_bot_inventory",
        "live_execution_allowed",
    )
    if safety.get("read_only") is not True:
        raise RuntimeError("readonly_audit_payload_not_read_only")
    for key in required_false:
        if safety.get(key) is not False:
            raise RuntimeError(f"readonly_audit_safety_rejected:{key}")


def _aad(*, request_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": ENVELOPE_SCHEMA,
            "request_id": request_id,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encrypt_audit(
    audit: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    validate_audit(audit)
    request_id, recipient_raw, recipient_key_id = validate_request(request)
    plaintext = json.dumps(
        dict(audit),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = _aad(request_id=request_id, recipient_key_id=recipient_key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    return {
        "schema": ENVELOPE_SCHEMA,
        "request_id": request_id,
        "generated_at_utc": _iso_now(),
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "plaintext_bytes": len(plaintext),
        "plaintext_published": False,
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    envelope = encrypt_audit(_load(args.audit), _load(args.request))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": "mmibkr.readonly_audit_encrypted_return_receipt.v1",
                "request_id": envelope["request_id"],
                "recipient_key_id": envelope["recipient_key_id"],
                "ciphertext_sha256": envelope["ciphertext_sha256"],
                "plaintext_bytes": envelope["plaintext_bytes"],
                "plaintext_published": False,
                "broker_mutation_authority": False,
                "live_execution_allowed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
