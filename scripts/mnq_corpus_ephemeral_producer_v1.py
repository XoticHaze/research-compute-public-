from __future__ import annotations

"""Deterministic producer for the fixed MNQ corpus ephemeral rendezvous.

This module owns transport only. It takes the public one-run recipient emitted
by the canonical session plus an already-authorized ephemeral download URL for
the frozen Foundry archive, encrypts the fixed artifact-fetch ticket, and
materializes only ciphertext chunks + a sanitized envelope.

No StrategySpec/runtime/broker/promotion/live authority is introduced.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

import ephemeral_x25519_chunked_v1 as transport
import mnq_corpus_ephemeral_consumer_v1 as corpus

RECIPIENT_SCHEMA = "mnq-corpus-ephemeral-recipient-v1"
RECIPIENT_FIELDS = {"schema", "run_id", "recipient_b64", "recipient_key_id"}
TICKET_FIELDS = {"schema", "download_url", "artifact_archive_sha256"}
AUTHORITY = "research_only"


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def validate_download_url(value: str) -> str:
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".oaiusercontent.com"):
        raise RuntimeError("mnq_corpus_download_url_rejected")
    return str(value)


def validate_recipient(node: dict) -> dict:
    if not isinstance(node, dict) or set(node) != RECIPIENT_FIELDS:
        raise RuntimeError("mnq_corpus_recipient_field_set_rejected")
    if node.get("schema") != RECIPIENT_SCHEMA:
        raise RuntimeError("mnq_corpus_recipient_schema_rejected")
    run_id = str(node.get("run_id") or "")
    if not run_id.isdigit():
        raise RuntimeError("mnq_corpus_recipient_run_id_rejected")
    raw = _b64d(str(node.get("recipient_b64") or ""))
    if len(raw) != 32:
        raise RuntimeError("mnq_corpus_recipient_key_rejected")
    key_id = "sha256:" + hashlib.sha256(raw).hexdigest()
    if str(node.get("recipient_key_id") or "") != key_id:
        raise RuntimeError("mnq_corpus_recipient_key_id_rejected")
    return {
        "run_id": run_id,
        "recipient_raw": raw,
        "recipient_key_id": key_id,
    }


def build_ticket(*, download_url: str, artifact_archive_sha256: str) -> bytes:
    if str(artifact_archive_sha256).lower() != corpus.ARCHIVE_SHA256:
        raise RuntimeError("mnq_corpus_archive_sha_rejected")
    node = {
        "schema": corpus.TICKET_SCHEMA,
        "download_url": validate_download_url(download_url),
        "artifact_archive_sha256": corpus.ARCHIVE_SHA256,
    }
    if set(node) != TICKET_FIELDS:
        raise AssertionError("ticket field set drift")
    return json.dumps(node, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_response(
    *,
    recipient: dict,
    download_url: str,
    artifact_archive_sha256: str,
    chunk_chars: int = transport.DEFAULT_CHUNK_CHARS,
) -> dict:
    valid = validate_recipient(recipient)
    run_id = valid["run_id"]
    recipient_raw = valid["recipient_raw"]
    recipient_key_id = valid["recipient_key_id"]
    plaintext = build_ticket(
        download_url=download_url,
        artifact_archive_sha256=artifact_archive_sha256,
    )

    recipient_key = x25519.X25519PublicKey.from_public_bytes(recipient_raw)
    sender = x25519.X25519PrivateKey.generate()
    sender_public_raw = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = transport.aad_bytes(
        schema=corpus.SCHEMA,
        run_id=run_id,
        harness=corpus.HARNESS,
        recipient_key_id=recipient_key_id,
        authority=AUTHORITY,
    )
    shared = sender.exchange(recipient_key)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(transport.derive_key(shared, aad)).encrypt(
        nonce,
        plaintext,
        aad,
    )
    response_root = f"rendezvous/responses/{run_id}"
    chunk_files, chunks = transport.build_text_chunk_manifest(
        base64.b64encode(ciphertext).decode("ascii"),
        response_root=response_root,
        stem="mnq-corpus-chunk",
        chunk_chars=chunk_chars,
    )
    envelope = {
        "schema": corpus.SCHEMA,
        "run_id": run_id,
        "authority": AUTHORITY,
        "harness": corpus.HARNESS,
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_public_raw).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": chunks,
    }
    transport.validate_envelope(
        envelope,
        expected_schema=corpus.SCHEMA,
        expected_run_id=run_id,
        expected_harness=corpus.HARNESS,
        response_root=response_root,
        expected_authority=AUTHORITY,
    )
    return {
        "run_id": run_id,
        "response_root": response_root,
        "chunk_files": chunk_files,
        "envelope": envelope,
    }


def write_response(result: dict, output_root: Path) -> dict:
    output_root = output_root.resolve()
    run_id = str(result["run_id"])
    response_root = str(result["response_root"])
    prefix = "rendezvous/responses/"
    if not response_root.startswith(prefix) or response_root != f"{prefix}{run_id}":
        raise RuntimeError("mnq_corpus_response_root_rejected")

    written: list[str] = []
    for path, text in result["chunk_files"]:
        target = (output_root / path).resolve()
        if output_root not in target.parents:
            raise RuntimeError("mnq_corpus_output_path_rejected")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="ascii")
        written.append(path)

    envelope_path = f"{response_root}/mnq-corpus-envelope.json"
    target = (output_root / envelope_path).resolve()
    if output_root not in target.parents:
        raise RuntimeError("mnq_corpus_output_path_rejected")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result["envelope"], sort_keys=True) + "\n", encoding="utf-8")
    written.append(envelope_path)

    return {
        "schema": "mnq-corpus-ephemeral-producer-receipt-v1",
        "run_id": run_id,
        "response_root": response_root,
        "files": written,
        "artifact_archive_sha256": corpus.ARCHIVE_SHA256,
        "authority": AUTHORITY,
        "strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "promotion_mutation": False,
        "live_trading": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", type=Path, required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--artifact-archive-sha256", default=corpus.ARCHIVE_SHA256)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--chunk-chars", type=int, default=transport.DEFAULT_CHUNK_CHARS)
    args = parser.parse_args()

    recipient = json.loads(args.recipient.read_text(encoding="utf-8"))
    result = build_response(
        recipient=recipient,
        download_url=args.download_url,
        artifact_archive_sha256=args.artifact_archive_sha256,
        chunk_chars=args.chunk_chars,
    )
    receipt = write_response(result, args.output_root)
    print("MNQ_CORPUS_EPHEMERAL_PRODUCER_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
