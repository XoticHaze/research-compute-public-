#!/usr/bin/env python3
from __future__ import annotations

"""Decrypt one run-bound P04 R3 causal packet and execute the frozen public guard."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import p04_r3_prospective_causal_guard_v1 as guard

RECIPIENT_SCHEMA = "p04-r3-prospective-current-recipient-v1"
ENVELOPE_SCHEMA = "p04-r3-prospective-current-x25519-v1"
RECEIPT_SCHEMA = "public.p04_r3_prospective_current_receipt.v1"
HARNESS = "p04_r3_prospective_current_v1"
AUTHORITY = "research_shadow_only"
GUARD_BLOB_SHA1 = "30acfe57130011837758b23f7c32367c717f00a7"
INFO = b"commandcenter-p04-r3-prospective-current-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def aad(run_id: str, recipient_key_id: str, event_id: str) -> bytes:
    return _canonical(
        {
            "schema": ENVELOPE_SCHEMA,
            "run_id": str(run_id),
            "harness": HARNESS,
            "authority": AUTHORITY,
            "guard_blob_sha1": GUARD_BLOB_SHA1,
            "recipient_key_id": recipient_key_id,
            "query_event_id": event_id,
        }
    )


def recipient_document(run_id: str, private_key: x25519.X25519PrivateKey) -> dict[str, Any]:
    raw = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {
        "schema": RECIPIENT_SCHEMA,
        "run_id": str(run_id),
        "harness": HARNESS,
        "guard_blob_sha1": GUARD_BLOB_SHA1,
        "recipient_b64": base64.b64encode(raw).decode("ascii"),
        "recipient_key_id": "sha256:" + _sha(raw),
    }


def decrypt_packet(
    envelope: dict[str, Any],
    ciphertext: bytes,
    private_raw: bytes,
    *,
    run_id: str,
) -> dict[str, Any]:
    required = {
        "schema",
        "run_id",
        "harness",
        "authority",
        "guard_blob_sha1",
        "recipient_key_id",
        "query_event_id",
        "sender_public_b64",
        "nonce_b64",
        "plaintext_sha256",
        "ciphertext_sha256",
        "chunks",
    }
    if set(envelope) != required:
        raise ValueError("envelope field set mismatch")
    if envelope["schema"] != ENVELOPE_SCHEMA or envelope["harness"] != HARNESS:
        raise ValueError("envelope contract mismatch")
    if envelope["authority"] != AUTHORITY:
        raise ValueError("envelope authority mismatch")
    if envelope["guard_blob_sha1"] != GUARD_BLOB_SHA1:
        raise ValueError("guard identity drift")
    if str(envelope["run_id"]) != str(run_id):
        raise ValueError("run identity mismatch")
    if _sha(ciphertext) != envelope["ciphertext_sha256"]:
        raise ValueError("ciphertext digest mismatch")
    if len(private_raw) != 32:
        raise ValueError("recipient private key length invalid")

    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    recipient_key_id = "sha256:" + _sha(recipient_public)
    if envelope["recipient_key_id"] != recipient_key_id:
        raise ValueError("recipient fingerprint mismatch")
    sender_raw = base64.b64decode(str(envelope["sender_public_b64"]), validate=True)
    if len(sender_raw) != 32:
        raise ValueError("sender public key length invalid")
    event_id = str(envelope["query_event_id"])
    if not event_id:
        raise ValueError("query event identity missing")
    bound_aad = aad(str(run_id), recipient_key_id, event_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(bound_aad).digest(),
        info=INFO,
    ).derive(shared)
    plaintext = ChaCha20Poly1305(key).decrypt(
        base64.b64decode(str(envelope["nonce_b64"]), validate=True),
        ciphertext,
        bound_aad,
    )
    if _sha(plaintext) != envelope["plaintext_sha256"]:
        raise ValueError("plaintext digest mismatch")
    packet = json.loads(plaintext)
    if not isinstance(packet, dict) or packet.get("schema") != guard.SCHEMA:
        raise ValueError("decrypted packet schema mismatch")
    query = packet.get("query")
    if not isinstance(query, dict) or query.get("event_id") != event_id:
        raise ValueError("decrypted packet event identity mismatch")
    return packet


def evaluate(
    envelope: dict[str, Any],
    ciphertext: bytes,
    private_raw: bytes,
    *,
    run_id: str,
) -> dict[str, Any]:
    packet = decrypt_packet(envelope, ciphertext, private_raw, run_id=run_id)
    decision = guard.validate_and_evaluate(packet)
    return {
        "schema": RECEIPT_SCHEMA,
        "run_id": str(run_id),
        "query_event_id": packet["query"]["event_id"],
        "packet_sha256": _sha(_canonical(packet)),
        "guard_blob_sha1": GUARD_BLOB_SHA1,
        "decision": decision,
        "authority": {
            "research_shadow_only": True,
            "promotion_authority": False,
            "allocation_authority": False,
            "strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "live_trading_change": False,
        },
    }


def _synthetic_packet() -> dict[str, Any]:
    query_ts = "2026-09-14T14:00:00+00:00"
    state_ts = "2026-09-14T13:48:00+00:00"
    query = {
        "event_id": "self-test-query",
        "trade_id": "self-test-trade",
        "event_timestamp": query_ts,
        "source_contract": "MNQ TEST",
        "dca_step": 1,
        "state_bar_timestamp": state_ts,
        "state_features": [0.01, 0.02, 0.03, 0.01, 0.02, 0.03],
        "query_year_scale": [1, 1, 1, 1, 1, 1],
        "regime": 0,
        "h24_score_timestamp": state_ts,
        "h24_score": 1.5,
        "h24_bucket": 4,
        "h24_model_sha256": guard.H24_MODEL_SHA256,
    }
    pool = []
    for i in range(8):
        increment = 10.0 if i < 6 else -2.0
        pool.append(
            {
                "event_id": f"self-test-neighbor-{i}",
                "trade_id": f"self-test-history-{i}",
                "event_timestamp": f"2026-09-{i+1:02d}T12:00:00+00:00",
                "source_contract": "MNQ HIST",
                "dca_step": 1,
                "regime": 0,
                "state_features": [0.01 + i / 1000, 0.02, 0.03, 0.01, 0.02, 0.03],
                "source_trade_exit_timestamp": f"2026-09-{i+1:02d}T13:00:00+00:00",
                "incremental_exit_points": increment,
                "positive_extra": increment > 0,
                "h24_bucket": 4 if i < 5 else 3,
            }
        )
    return {
        "schema": guard.SCHEMA,
        "anchors": guard._anchors(),
        "candidate_pool_complete": True,
        "candidate_pool_digest": guard._digest(pool),
        "query": query,
        "candidate_pool": pool,
    }


def self_test() -> None:
    run_id = "self-test-run"
    private = x25519.X25519PrivateKey.generate()
    recipient = recipient_document(run_id, private)
    packet = _synthetic_packet()
    plaintext = _canonical(packet)
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    recipient_raw = base64.b64decode(recipient["recipient_b64"])
    bound_aad = aad(run_id, recipient["recipient_key_id"], packet["query"]["event_id"])
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(bound_aad).digest(),
        info=INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, bound_aad)
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "run_id": run_id,
        "harness": HARNESS,
        "authority": AUTHORITY,
        "guard_blob_sha1": GUARD_BLOB_SHA1,
        "recipient_key_id": recipient["recipient_key_id"],
        "query_event_id": packet["query"]["event_id"],
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "plaintext_sha256": _sha(plaintext),
        "ciphertext_sha256": _sha(ciphertext),
        "chunks": [{"path": "self-test", "sha256": "self-test", "chars": 1}],
    }
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    receipt = evaluate(envelope, ciphertext, private_raw, run_id=run_id)
    assert receipt["decision"]["shadow_decision"] == "RELEASE"
    assert receipt["decision"]["positive_neighbors"] == 6
    assert receipt["decision"]["same_h24_bucket_neighbors"] == 5

    bad = dict(envelope)
    bad["guard_blob_sha1"] = "0" * 40
    try:
        decrypt_packet(bad, ciphertext, private_raw, run_id=run_id)
    except ValueError as exc:
        assert "guard identity drift" in str(exc)
    else:
        raise AssertionError("guard identity drift was accepted")

    print("P04_R3_PROSPECTIVE_CURRENT_CONSUMER=PASS")
    print(json.dumps(receipt, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["self-test", "consume"])
    parser.add_argument("--envelope", type=Path)
    parser.add_argument("--ciphertext", type=Path)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0
    if not all((args.envelope, args.ciphertext, args.private_key, args.run_id, args.output)):
        raise SystemExit("consume requires --envelope --ciphertext --private-key --run-id --output")
    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    receipt = evaluate(
        envelope,
        args.ciphertext.read_bytes(),
        args.private_key.read_bytes(),
        run_id=str(args.run_id),
    )
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
