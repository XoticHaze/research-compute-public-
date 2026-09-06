from __future__ import annotations

"""Public-safe sender for one-run PR285 X25519 envelopes.

This contains no private data or credentials. A private authority supplies a payload path
and the run's published recipient JSON; this helper emits only the encrypted envelope.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from pr285_ephemeral_consumer_v1 import SCHEMA, HARNESS, _aad, _derive


def build_envelope(payload_path: Path, recipient_path: Path) -> dict:
    recipient = json.loads(recipient_path.read_text(encoding="utf-8"))
    if recipient.get("schema") != "pr285-ephemeral-recipient-v1":
        raise RuntimeError("recipient schema mismatch")
    run_id = str(recipient["run_id"])
    recipient_raw = base64.b64decode(recipient["recipient_b64"], validate=True)
    if len(recipient_raw) != 32:
        raise RuntimeError("recipient public key length invalid")
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if recipient.get("recipient_key_id") != key_id:
        raise RuntimeError("recipient fingerprint mismatch")

    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    aad = _aad(run_id, key_id)
    key = _derive(shared, aad)
    nonce = os.urandom(12)
    plaintext = payload_path.read_bytes()
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "authority": "research_only",
        "harness": HARNESS,
        "recipient_key_id": key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--payload", required=True)
    p.add_argument("--recipient", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    envelope = build_envelope(Path(args.payload), Path(args.recipient))
    Path(args.output).write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": envelope["schema"],
        "run_id": envelope["run_id"],
        "recipient_key_id": envelope["recipient_key_id"],
        "plaintext_sha256": envelope["plaintext_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
