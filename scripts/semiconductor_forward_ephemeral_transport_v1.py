from __future__ import annotations

"""Public-safe two-way X25519 transport helper for semiconductor forward compute."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "semiconductor-forward-ephemeral-x25519-v1"
RETURN_SCHEMA = "semiconductor-forward-return-x25519-v1"
HARNESS = "semiconductor_external_forward_three_book_v1"
INFO = b"research-foundry-semiconductor-forward-ephemeral-v1"
RETURN_INFO = b"research-foundry-semiconductor-forward-return-v1"


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _key_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _aad(schema: str, run_id: str, key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": schema,
            "run_id": str(run_id),
            "authority": "research_only",
            "harness": HARNESS,
            "recipient_key_id": key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=info,
    ).derive(shared)


def generate_return_key(private_key_path: Path, public_record_path: Path) -> dict:
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    private_key_path.write_text(base64.b64encode(private_raw).decode("ascii"), encoding="ascii")
    record = {
        "schema": "semiconductor-forward-return-recipient-v1",
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": _key_id(public_raw),
    }
    public_record_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    return record


def encrypt_input(payload_path: Path, run_recipient_path: Path, output_path: Path) -> dict:
    recipient = json.loads(run_recipient_path.read_text(encoding="utf-8"))
    if recipient.get("schema") != "semiconductor-forward-ephemeral-recipient-v1":
        raise RuntimeError("run recipient schema mismatch")
    run_id = str(recipient["run_id"])
    recipient_raw = _b64d(recipient["recipient_b64"])
    if len(recipient_raw) != 32:
        raise RuntimeError("run recipient public key invalid")
    key_id = _key_id(recipient_raw)
    if recipient.get("recipient_key_id") != key_id:
        raise RuntimeError("run recipient fingerprint mismatch")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = _aad(SCHEMA, run_id, key_id)
    key = _derive(
        sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw)),
        aad,
        INFO,
    )
    nonce = os.urandom(12)
    plaintext = payload_path.read_bytes()
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    env = {
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
    output_path.write_text(json.dumps(env, sort_keys=True) + "\n", encoding="utf-8")
    return {"run_id": run_id, "plaintext_sha256": env["plaintext_sha256"]}


def decrypt_return(envelope_path: Path, private_key_path: Path, output_path: Path) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    if env.get("schema") != RETURN_SCHEMA or env.get("authority") != "research_only":
        raise RuntimeError("return envelope identity mismatch")
    if env.get("harness") != HARNESS:
        raise RuntimeError("return harness mismatch")
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    key_id = _key_id(public_raw)
    if env.get("recipient_key_id") != key_id:
        raise RuntimeError("return recipient fingerprint mismatch")
    sender_raw = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    ciphertext = _b64d(env["ciphertext_b64"])
    aad = _aad(RETURN_SCHEMA, str(env["run_id"]), key_id)
    key = _derive(
        private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw)),
        aad,
        RETURN_INFO,
    )
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("return plaintext digest mismatch")
    output_path.write_bytes(plaintext)
    return {"run_id": str(env["run_id"]), "plaintext_sha256": env["plaintext_sha256"]}


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    key = sub.add_parser("generate-return-key")
    key.add_argument("--private", required=True)
    key.add_argument("--public", required=True)
    enc = sub.add_parser("encrypt-input")
    enc.add_argument("--payload", required=True)
    enc.add_argument("--run-recipient", required=True)
    enc.add_argument("--output", required=True)
    dec = sub.add_parser("decrypt-return")
    dec.add_argument("--envelope", required=True)
    dec.add_argument("--private", required=True)
    dec.add_argument("--output", required=True)
    args = p.parse_args()
    if args.command == "generate-return-key":
        result = generate_return_key(Path(args.private), Path(args.public))
    elif args.command == "encrypt-input":
        result = encrypt_input(Path(args.payload), Path(args.run_recipient), Path(args.output))
    else:
        result = decrypt_return(Path(args.envelope), Path(args.private), Path(args.output))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
