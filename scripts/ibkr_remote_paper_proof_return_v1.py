from __future__ import annotations

"""Encrypt one selected-runtime paper-proof receipt to its private one-run recipient.

This helper never calls the broker and never changes strategy or execution policy.
It only validates the already-produced public proof receipt against the materialized
command identity and encrypts the receipt for the private MM-IBKR producer.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

RECEIPT_SCHEMA = "mmibkr.remote_selected_runtime_paper_proof_receipt.v1"
EXECUTE_RECEIPT_SCHEMA = "mmibkr.remote_selected_runtime_paper_execute_receipt.v1"
RECEIPT_SCHEMAS = {RECEIPT_SCHEMA, EXECUTE_RECEIPT_SCHEMA}
RETURN_RECIPIENT_SCHEMA = "ibkr-remote-paper-return-recipient-v1"
RETURN_ENVELOPE_SCHEMA = "ibkr-remote-paper-proof-return-x25519-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mm_ibkr_remote_paper_runtime_v1"
RETURN_INFO = b"mm-ibkr-paper-proof-return-v1"
CHUNK_CHARS = 8000


def _aad(*, run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": RETURN_ENVELOPE_SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_receipt(receipt: Any, runtime: Mapping[str, Any], *, run_id: str) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or receipt.get("schema") not in RECEIPT_SCHEMAS:
        raise RuntimeError("selected-runtime encrypted return receipt schema mismatch")
    expected_schema = RECEIPT_SCHEMA if runtime.get("mode") == "paper_submit_proof" else EXECUTE_RECEIPT_SCHEMA
    if receipt.get("schema") != expected_schema:
        raise RuntimeError("selected-runtime encrypted return mode/receipt schema mismatch")
    if str((receipt.get("github") or {}).get("run_id") or "") != str(run_id):
        raise RuntimeError("selected-runtime proof receipt run id mismatch")
    command = receipt.get("command") if isinstance(receipt.get("command"), Mapping) else {}
    if str(command.get("command_id") or "") != str(runtime.get("command_id") or ""):
        raise RuntimeError("selected-runtime proof receipt command id mismatch")
    authority = receipt.get("authority") if isinstance(receipt.get("authority"), Mapping) else {}
    if authority.get("cloud_strategy_authority") is not False:
        raise RuntimeError("cloud strategy authority boundary violated")
    if authority.get("cloud_execution_policy_authority") is not False:
        raise RuntimeError("cloud execution policy authority boundary violated")
    if authority.get("direct_broker_client_used") is not False:
        raise RuntimeError("direct broker client boundary violated")
    if authority.get("global_cancel_allowed") is not False:
        raise RuntimeError("global cancel boundary violated")
    if authority.get("live_execution_allowed") is not False:
        raise RuntimeError("live execution boundary violated")
    cleanup = receipt.get("cleanup") if isinstance(receipt.get("cleanup"), Mapping) else {}
    if cleanup.get("global_cancel_called") is not False:
        raise RuntimeError("global cancel was called")
    return dict(receipt)


def encrypt_receipt(
    *,
    receipt: Mapping[str, Any],
    runtime: Mapping[str, Any],
    recipient: Mapping[str, Any],
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    clean = validate_receipt(receipt, runtime, run_id=run_id)
    if recipient.get("schema") != RETURN_RECIPIENT_SCHEMA:
        raise RuntimeError("proof return recipient schema mismatch")
    try:
        raw_recipient = base64.b64decode(str(recipient.get("recipient_b64") or "").encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("proof return recipient key encoding invalid") from exc
    if len(raw_recipient) != 32:
        raise RuntimeError("proof return recipient key length invalid")
    recipient_key_id = "sha256:" + hashlib.sha256(raw_recipient).hexdigest()
    if recipient_key_id != recipient.get("recipient_key_id"):
        raise RuntimeError("proof return recipient fingerprint mismatch")

    plaintext = json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aad = _aad(run_id=run_id, recipient_key_id=recipient_key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(raw_recipient))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=RETURN_INFO).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    payload_b64 = base64.b64encode(ciphertext).decode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    manifest: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(payload_b64), CHUNK_CHARS)):
        text = payload_b64[start:start + CHUNK_CHARS]
        local_name = f"ibkr-paper-proof-{index:03d}.txt"
        path = output_dir / local_name
        path.write_text(text, encoding="ascii")
        os.chmod(path, 0o600)
        manifest.append({
            "path": f"rendezvous/returns/{run_id}/{local_name}",
            "local_name": local_name,
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
            "chars": len(text),
        })

    envelope = {
        "schema": RETURN_ENVELOPE_SCHEMA,
        "run_id": str(run_id),
        "authority": AUTHORITY,
        "harness": HARNESS,
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": manifest,
    }
    envelope_path = output_dir / "ibkr-paper-proof-envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(envelope_path, 0o600)
    return envelope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    recipient_path = Path(str(runtime.get("return_recipient_path") or ""))
    if runtime.get("encrypted_return_requested") is not True or not recipient_path.is_file():
        raise SystemExit("selected-runtime proof encrypted return was not materialized")
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    recipient = json.loads(recipient_path.read_text(encoding="utf-8"))
    envelope = encrypt_receipt(
        receipt=receipt,
        runtime=runtime,
        recipient=recipient,
        run_id=args.run_id,
        output_dir=Path(args.output_dir),
    )
    print("IBKR_REMOTE_PROOF_RETURN_READY=" + json.dumps({
        "run_id": str(args.run_id),
        "command_id": runtime.get("command_id"),
        "ciphertext_sha256": envelope["ciphertext_sha256"],
        "plaintext_sha256": envelope["plaintext_sha256"],
        "chunks": len(envelope["chunks"]),
        "plaintext_published": False,
        "broker_action": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
