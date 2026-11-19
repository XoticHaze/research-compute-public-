#!/usr/bin/env python3
"""Consume a run-bound private IBKR B1 OHLCV return in an authenticated private runtime.

No broker access, orders, credential fetching, network calls or public OHLC.
The one-run recipient key must have been generated/custodied by the consumer.
Raw results go to an exclusive mode-0600 local file, never to stdout.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts.ibkr_b1_market_bars_return_v1 import (
    ENVELOPE_SCHEMA, RESULT_SCHEMA, TRANSPORT_INFO, MAX_RAW_BYTES,
    MAX_ROWS, MAX_CHUNKS, _aad
)
from research.forward_bar_contract_v2 import REQUIRED_COLUMNS, normalize_frame

RUN_ID_RE = re.compile(r"^[0-9]{8,24}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
CHUNK_NAME = re.compile(r"^ibkr-market-bars-[0-9]{3}\.txt$")
MAX_CHUNK_CHARS = 16000


def _load_envelope(folder: Path) -> dict[str, Any]:
    path = folder / "ibkr-warm-read-envelope.json"
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 20000:
        raise ValueError("market_bars_envelope_unavailable")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (type(value) is not dict or set(value) != {
        "schema", "run_id", "recipient_key_id", "sender_public_b64",
        "nonce_b64", "ciphertext_sha256", "compression", "chunks"
    } or value.get("schema") != ENVELOPE_SCHEMA or value.get("compression") != "zlib"):
        raise ValueError("market_bars_envelope_shape_invalid")
    return value


def _recipient(private_key_file: Path, key_id: str) -> x25519.X25519PrivateKey:
    if private_key_file.is_symlink() or not private_key_file.is_file():
        raise ValueError("market_bars_recipient_file_unavailable")
    st = private_key_file.stat()
    if st.st_uid != os.geteuid() or st.st_mode & 0o077 or st.st_size > 160:
        raise ValueError("market_bars_recipient_file_untrusted")
    encoded = private_key_file.read_text(encoding="ascii").strip()
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("market_bars_recipient_encoding_invalid") from exc
    if len(raw) != 32:
        raise ValueError("market_bars_recipient_size_invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(raw)
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if "sha256:" + hashlib.sha256(public).hexdigest() != key_id:
        raise ValueError("market_bars_recipient_fingerprint_mismatch")
    return private


def _assemble(folder: Path, envelope: dict[str, Any], run_id: str) -> bytes:
    chunks = envelope["chunks"]
    if type(chunks) is not list or not 1 <= len(chunks) <= MAX_CHUNKS:
        raise ValueError("market_bars_chunk_count_invalid")
    pieces = []
    seen = set()
    for i, item in enumerate(chunks):
        if type(item) is not dict or set(item) != {"path", "local_name", "sha256", "chars"}:
            raise ValueError("market_bars_chunk_descriptor_invalid")
        filename = item["local_name"]
        if (type(filename) is not str or not CHUNK_NAME.fullmatch(filename)
                or filename in seen or filename != f"ibkr-market-bars-{i:03d}.txt"):
            raise ValueError("market_bars_chunk_name_invalid")
        seen.add(filename)
        if item["path"] != f"rendezvous/returns/{run_id}/{filename}":
            raise ValueError("market_bars_chunk_path_invalid")
        chars = item["chars"]
        if type(chars) is not int or not 0 < chars <= MAX_CHUNK_CHARS:
            raise ValueError("market_bars_chunk_size_invalid")
        path = folder / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size != chars:
            raise ValueError("market_bars_chunk_missing")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("market_bars_chunk_digest_mismatch")
        pieces.append(raw)
    try:
        raw = base64.b64decode(b"".join(pieces), validate=True)
    except Exception as exc:
        raise ValueError("market_bars_ciphertext_encoding_invalid") from exc
    if hashlib.sha256(raw).hexdigest() != envelope["ciphertext_sha256"]:
        raise ValueError("market_bars_ciphertext_integrity_invalid")
    return raw


def _decompress_bounded(data: bytes) -> bytes:
    if len(data) > MAX_RAW_BYTES:
        raise ValueError("market_bars_compressed_payload_oversized")
    decoder = zlib.decompressobj()
    plaintext = decoder.decompress(data, MAX_RAW_BYTES + 1)
    if len(plaintext) > MAX_RAW_BYTES or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
        raise ValueError("market_bars_decompression_unbounded")
    plaintext += decoder.flush()
    if len(plaintext) > MAX_RAW_BYTES:
        raise ValueError("market_bars_plaintext_oversized")
    return plaintext


def decode(*, folder: Path, private_key_file: Path,
           expected_run_id: str, expected_public_head: str,
           expected_symbols: tuple[str, ...]) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(expected_run_id) or not HEAD_RE.fullmatch(expected_public_head):
        raise ValueError("market_bars_expected_run_head_invalid")
    if not expected_symbols or len(set(expected_symbols)) != len(expected_symbols):
        raise ValueError("market_bars_expected_symbol_scope_invalid")
    envelope = _load_envelope(folder)
    if str(envelope.get("run_id")) != expected_run_id:
        raise ValueError("market_bars_envelope_run_mismatch")
    private = _recipient(private_key_file, envelope["recipient_key_id"])
    ciphertext = _assemble(folder, envelope, expected_run_id)
    try:
        sender = x25519.X25519PublicKey.from_public_bytes(
            base64.b64decode(envelope["sender_public_b64"], validate=True))
        nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
        if len(nonce) != 12:
            raise ValueError("market_bars_nonce_invalid")
        aad = _aad(run_id=expected_run_id, recipient_key_id=envelope["recipient_key_id"])
        key = HKDF(algorithm=hashes.SHA256(), length=32,
                   salt=hashlib.sha256(aad).digest(), info=TRANSPORT_INFO).derive(
                       private.exchange(sender))
        compressed = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise ValueError("market_bars_authenticated_decrypt_failed") from exc
    payload = json.loads(_decompress_bounded(compressed))
    if (type(payload) is not dict or set(payload) != {
        "schema", "run_id", "public_head", "generated_at_utc", "forward_bar_contract",
        "row_count", "contracts", "bars", "read_only", "broker_mutation_authority"
    } or payload["schema"] != RESULT_SCHEMA
            or str(payload["run_id"]) != expected_run_id
            or payload["public_head"] != expected_public_head
            or payload["forward_bar_contract"] != "research.forward_bar.v2"
            or payload["read_only"] is not True
            or payload["broker_mutation_authority"] is not False):
        raise ValueError("market_bars_payload_identity_invalid")
    contracts = payload["contracts"]
    bars = payload["bars"]
    if (type(contracts) is not list or type(bars) is not list
            or not 1 <= len(bars) <= MAX_ROWS
            or payload["row_count"] != len(bars)):
        raise ValueError("market_bars_payload_rows_invalid")
    if {str(c["symbol"]) for c in contracts} != set(expected_symbols):
        raise ValueError("market_bars_expected_contract_symbols_mismatch")
    allowed = {(str(c["symbol"]), str(c["asset_type"]), str(c["contract_id"]), str(c["bar_size"]))
               for c in contracts}
    if any(type(row) is not dict or set(row) != set(REQUIRED_COLUMNS) for row in bars):
        raise ValueError("market_bars_row_schema_invalid")
    if any((r["symbol"], r["asset_type"], r["contract_id"], r["bar_size"]) not in allowed or r["source"] != "ibkr"
           for r in bars):
        raise ValueError("market_bars_unqualified_contract_result")
    normalize_frame(bars)
    generated = datetime.fromisoformat(str(payload["generated_at_utc"]).replace("Z", "+00:00"))
    if generated.tzinfo is None or generated.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("market_bars_generated_timestamp_invalid")
    return payload


def store_private_rows(payload: dict[str, Any], output_file: Path) -> None:
    parent = output_file.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("market_bars_output_parent_invalid")
    pst = parent.stat()
    if pst.st_uid != os.geteuid() or pst.st_mode & 0o022:
        raise ValueError("market_bars_output_parent_untrusted")
    fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            for row in payload["bars"]:
                fh.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        output_file.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    for key in ("return-dir", "recipient-private-key", "expected-run-id",
                "expected-public-head", "expected-symbols", "private-output"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    names = tuple(x.strip().upper() for x in args.expected_symbols.split(",") if x.strip())
    payload = decode(
        folder=Path(args.return_dir), private_key_file=Path(args.recipient_private_key),
        expected_run_id=args.expected_run_id, expected_public_head=args.expected_public_head,
        expected_symbols=names,
    )
    store_private_rows(payload, Path(args.private_output))
    print("IBKR_PRIVATE_BARS_CONSUMED=" + json.dumps({
        "schema": "mmibkr.ibkr_private_bars_consumer_receipt.v1",
        "run_id": payload["run_id"],
        "row_count": payload["row_count"],
        "contract_count": len(payload["contracts"]),
        "private_file_written": True,
        "plaintext_published": False,
        "broker_action": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
