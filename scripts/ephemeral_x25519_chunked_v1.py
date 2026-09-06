from __future__ import annotations

"""Transport-only primitives for run-bound encrypted research capsules.

This module decrypts authenticated ciphertext but deliberately owns no workload
execution authority. Fixed consumers must separately validate the plaintext file
set, provenance and scientific contract before executing or emitting a receipt.
"""

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUTHORITY = "research_only"
INFO = b"commandcenter-ephemeral-chunked-v1"
ENVELOPE_FIELDS = {
    "schema",
    "run_id",
    "authority",
    "harness",
    "recipient_key_id",
    "sender_public_b64",
    "nonce_b64",
    "ciphertext_sha256",
    "plaintext_sha256",
    "chunks",
}
CHUNK_FIELDS = {"path", "sha256", "chars"}


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def aad_bytes(*, schema: str, run_id: str, harness: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": schema,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": harness,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def derive_key(shared: bytes, aad: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)


def validate_envelope(
    envelope: dict,
    *,
    expected_schema: str,
    expected_run_id: str,
    expected_harness: str,
    response_root: str,
) -> None:
    if not isinstance(envelope, dict) or set(envelope) != ENVELOPE_FIELDS:
        raise RuntimeError("chunked envelope field set mismatch")
    if envelope["schema"] != expected_schema or str(envelope["run_id"]) != str(expected_run_id):
        raise RuntimeError("chunked envelope run/schema mismatch")
    if envelope["authority"] != AUTHORITY or envelope["harness"] != expected_harness:
        raise RuntimeError("chunked envelope authority/harness mismatch")
    if not str(envelope["recipient_key_id"]).startswith("sha256:"):
        raise RuntimeError("recipient key fingerprint invalid")
    chunks = envelope["chunks"]
    if not isinstance(chunks, list) or not chunks or len(chunks) > 64:
        raise RuntimeError("chunk list invalid")
    seen: set[str] = set()
    prefix = response_root.rstrip("/") + "/"
    for node in chunks:
        if not isinstance(node, dict) or set(node) != CHUNK_FIELDS:
            raise RuntimeError("chunk descriptor field set mismatch")
        path = str(node["path"])
        if not path.startswith(prefix) or "/../" in f"/{path}/" or path in seen:
            raise RuntimeError("chunk path invalid")
        seen.add(path)
        digest = str(node["sha256"])
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RuntimeError("chunk digest invalid")
        if int(node["chars"]) <= 0:
            raise RuntimeError("chunk length invalid")


def decrypt_assembled_ciphertext(
    *,
    envelope: dict,
    ciphertext: bytes,
    private_key_path: Path,
    expected_schema: str,
    expected_run_id: str,
    expected_harness: str,
    response_root: str,
) -> bytes:
    validate_envelope(
        envelope,
        expected_schema=expected_schema,
        expected_run_id=expected_run_id,
        expected_harness=expected_harness,
        response_root=response_root,
    )
    if sha256_bytes(ciphertext) != envelope["ciphertext_sha256"]:
        raise RuntimeError("assembled ciphertext digest mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    recipient_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if recipient_key_id != envelope["recipient_key_id"]:
        raise RuntimeError("recipient key fingerprint mismatch")

    sender_raw = _b64d(envelope["sender_public_b64"])
    nonce = _b64d(envelope["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce length invalid")
    aad = aad_bytes(
        schema=expected_schema,
        run_id=str(expected_run_id),
        harness=expected_harness,
        recipient_key_id=recipient_key_id,
    )
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(derive_key(shared, aad)).decrypt(nonce, ciphertext, aad)
    if sha256_bytes(plaintext) != envelope["plaintext_sha256"]:
        raise RuntimeError("decrypted plaintext digest mismatch")
    return plaintext
