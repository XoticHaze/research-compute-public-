from __future__ import annotations

"""One-run X25519 consumer for the fixed PR285 private research harness.

The public runner owns an ephemeral private key only for the lifetime of one job. The
private authority receives only the public key/fingerprint, encrypts the exact payload to
that run, and the consumer emits only the already-sanitized PR285 harness receipt.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import validate_sealed_job_v1 as sealed

SCHEMA = "pr285-ephemeral-x25519-v1"
HARNESS = "research_foundry_pr285_stage1_v1"
INFO = b"commandcenter-pr285-ephemeral-v1"


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": "research_only",
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes) -> bytes:
    salt = hashlib.sha256(aad).digest()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(shared)


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "run_id",
        "authority",
        "harness",
        "recipient_key_id",
        "sender_public_b64",
        "nonce_b64",
        "ciphertext_b64",
        "plaintext_sha256",
    }
    if set(env) != required:
        raise RuntimeError("ephemeral envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("ephemeral envelope run identity mismatch")
    if env["authority"] != "research_only" or env["harness"] != HARNESS:
        raise RuntimeError("ephemeral envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    expected_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != expected_key_id:
        raise RuntimeError("recipient key fingerprint mismatch")

    sender_raw = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    ciphertext = _b64d(env["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("ephemeral envelope key/nonce length invalid")
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    aad = _aad(str(expected_run_id), expected_key_id)
    key = _derive(shared, aad)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    payload = private_key_path.parent / "pr285-payload.tar.gz"
    payload.write_bytes(plaintext)
    try:
        return sealed.run_pr285(payload)
    finally:
        payload.unlink(missing_ok=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    result = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    out = {
        "schema": "pr285-sealed-consumer-receipt-v1",
        "authority": "research_only",
        "harness": result["harness"],
        "families": result["families"],
    }
    print("PR285_EPHEMERAL_RECEIPT=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
