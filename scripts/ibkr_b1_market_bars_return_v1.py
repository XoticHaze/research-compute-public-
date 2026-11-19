#!/usr/bin/env python3
"""Run-bound, encrypted market-bars-only return from an existing B1 post-auth handoff.

The broker reader has already completed its read. This module never opens an
IBKR connection, reads account/position/execution state or mutates the Gateway.
Only contract-qualified canonical forward bars enter the private ciphertext.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from research.forward_bar_contract_v2 import REQUIRED_COLUMNS, normalize_frame

RESULT_SCHEMA = "mmibkr.ibkr_private_market_bars.v1"
ENVELOPE_SCHEMA = "mmibkr.ibkr_private_bars_return_x25519.v1"
TRANSPORT_INFO = b"mmibkr-private-b1-market-bars-v1"
BAR_CONTRACT_SCHEMA = "research.forward_bar.v2"
CHUNK_CHARS = 16000
MAX_ROWS = 5000
MAX_RAW_BYTES = 4_000_000
MAX_CHUNKS = 64
RUN_ID = re.compile(r"^[0-9]{8,24}$")
HEAD = re.compile(r"^[0-9a-f]{40}$")
FORWARD_FIELDS = frozenset(REQUIRED_COLUMNS)


def _object(path: Path) -> dict[str, Any]:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES:
        raise ValueError("private_bars_handoff_size_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError("private_bars_handoff_object_required")
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES:
        raise ValueError("private_bars_rows_size_invalid")
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            if len(rows) >= MAX_ROWS:
                raise ValueError("private_bars_row_limit")
            row = json.loads(line)
            if type(row) is not dict or set(row) != FORWARD_FIELDS:
                raise ValueError("private_bars_forward_fields_invalid")
            rows.append(row)
    if not rows:
        raise ValueError("private_bars_rows_empty")
    return rows


def _bar_json(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in REQUIRED_COLUMNS:
        val = row[key]
        if key == "timestamp":
            result[key] = val.isoformat()
        elif key in ("open", "high", "low", "close"):
            val = float(val)
            if not math.isfinite(val) or val <= 0:
                raise ValueError("private_bars_price_invalid")
            result[key] = val
        elif key in ("volume", "wap", "bar_count"):
            val = float(val)
            result[key] = val if math.isfinite(val) else None
        else:
            result[key] = str(val)
    return result


def build_payload(*, handoff: Mapping[str, Any], rows: list[dict[str, Any]],
                  run_id: str, public_head: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(str(run_id)) or not HEAD.fullmatch(str(public_head)):
        raise ValueError("private_bars_run_or_head_invalid")
    if (handoff.get("schema") != "mmibkr-ibkr-post-auth-handoff-v2"
            or handoff.get("trading_mode") != "paper"
            or handoff.get("read_only") is not True
            or handoff.get("paper_account_verified") is not True
            or handoff.get("consumer_ready") is not True
            or handoff.get("bar_requests_explicit") is not True
            or handoff.get("forward_bar_contract") != BAR_CONTRACT_SCHEMA):
        raise ValueError("private_bars_broker_handoff_unqualified")
    caps = handoff.get("capabilities")
    if (not isinstance(caps, Mapping)
            or caps.get("historical_market_data") is not True
            or caps.get("canonical_forward_bar_materialization") is not True
            or caps.get("order_submission") is not False):
        raise ValueError("private_bars_broker_readonly_capability_unqualified")
    sym_receipts = handoff.get("symbols")
    requested = handoff.get("requested_symbols")
    if (not isinstance(sym_receipts, list) or not sym_receipts
            or not isinstance(requested, list) or len(requested) != len(sym_receipts)):
        raise ValueError("private_bars_symbol_receipts_missing")
    allowed: set[tuple[str, str, str, str]] = set()
    contracts: list[dict[str, Any]] = []
    for receipt in sym_receipts:
        if not isinstance(receipt, Mapping):
            raise ValueError("private_bars_symbol_receipt_invalid")
        symbol = str(receipt.get("symbol") or "").upper()
        if (symbol not in requested or receipt.get("contract_qualified") is not True
                or receipt.get("historical_data_ready") is not True):
            raise ValueError("private_bars_symbol_unqualified")
        reqs = receipt.get("bar_requests")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("private_bars_exact_requests_absent")
        for req in reqs:
            if not isinstance(req, Mapping):
                raise ValueError("private_bars_request_receipt_invalid")
            resolved = req.get("resolved_history_contract")
            if not isinstance(resolved, Mapping):
                raise ValueError("private_bars_history_contract_unqualified")
            typ = str(resolved.get("secType") or "").upper()
            if typ not in ("STK", "FUT", "OPT"):
                raise ValueError("private_bars_asset_type_invalid")
            cid = str(req.get("history_contract_id") or "")
            size = str(req.get("bar_size_setting") or "")
            if not cid.startswith("conid:") or not cid[6:].isdigit() or int(cid[6:]) <= 0:
                raise ValueError("private_bars_conid_missing")
            if not size or not req.get("duration_str"):
                raise ValueError("private_bars_timeframe_missing")
            identity = (symbol, typ, cid, size)
            if identity in allowed:
                raise ValueError("private_bars_duplicate_contract_window")
            allowed.add(identity)
            contracts.append({
                "symbol": symbol,
                "asset_type": typ,
                "contract_id": cid,
                "bar_size": size,
                "exchange": str(resolved.get("exchange") or ""),
                "expiry": str(resolved.get("lastTradeDateOrContractMonth") or ""),
                "right": str(resolved.get("right") or ""),
                "strike": resolved.get("strike"),
                "multiplier": str(resolved.get("multiplier") or ""),
            })
    if set(requested) != {p["symbol"] for p in contracts}:
        raise ValueError("private_bars_symbol_coverage_invalid")
    if not 0 < len(rows) <= MAX_ROWS:
        raise ValueError("private_bars_row_count_invalid")
    frame = normalize_frame(rows)
    if len(frame) != len(rows):
        raise ValueError("private_bars_normalization_dropped_rows")
    bars = [_bar_json(r) for r in frame.to_dict(orient="records")]
    observed = {(p["symbol"], p["asset_type"], p["contract_id"], p["bar_size"]) for p in bars}
    if not observed or not observed.issubset(allowed):
        raise ValueError("private_bars_contract_identity_drift")
    if set(requested) != {p["symbol"] for p in bars}:
        raise ValueError("private_bars_missing_requested_symbol_rows")
    if any(p["source"] != "ibkr" for p in bars):
        raise ValueError("private_bars_non_ibkr_source")
    if handoff.get("forward_bar_count") != len(bars):
        raise ValueError("private_bars_handoff_bar_count_mismatch")
    return {
        "schema": RESULT_SCHEMA,
        "run_id": str(run_id),
        "public_head": public_head,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "forward_bar_contract": BAR_CONTRACT_SCHEMA,
        "row_count": len(bars),
        "contracts": contracts,
        "bars": bars,
        "read_only": True,
        "broker_mutation_authority": False,
    }


def _aad(*, run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({
        "schema": ENVELOPE_SCHEMA, "run_id": str(run_id),
        "recipient_key_id": recipient_key_id
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encrypt_payload(*, payload: Mapping[str, Any], recipient_b64: str,
                    recipient_key_id: str, run_id: str, output_dir: Path) -> dict[str, Any]:
    if payload.get("schema") != RESULT_SCHEMA or payload.get("run_id") != str(run_id):
        raise ValueError("private_bars_payload_run_mismatch")
    if payload.get("broker_mutation_authority") is not False or payload.get("read_only") is not True:
        raise ValueError("private_bars_payload_mutation_boundary")
    try:
        recipient_raw = base64.b64decode(recipient_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("private_bars_recipient_invalid") from exc
    if len(recipient_raw) != 32 or recipient_key_id != "sha256:" + hashlib.sha256(recipient_raw).hexdigest():
        raise ValueError("private_bars_recipient_fingerprint_invalid")
    raw_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw_json) > MAX_RAW_BYTES:
        raise ValueError("private_bars_payload_oversized")
    compressed = zlib.compress(raw_json, level=9)
    sender = x25519.X25519PrivateKey.generate()
    sender_pub = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aad = _aad(run_id=run_id, recipient_key_id=recipient_key_id)
    key = HKDF(algorithm=hashes.SHA256(), length=32,
               salt=hashlib.sha256(aad).digest(), info=TRANSPORT_INFO).derive(
                   sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw)))
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, compressed, aad)
    b64 = base64.b64encode(ciphertext).decode("ascii")
    chunk_count = (len(b64) + CHUNK_CHARS - 1) // CHUNK_CHARS
    if not 1 <= chunk_count <= MAX_CHUNKS:
        raise ValueError("private_bars_transport_chunk_limit")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    chunks = []
    for n, start in enumerate(range(0, len(b64), CHUNK_CHARS)):
        value = b64[start:start + CHUNK_CHARS]
        filename = f"ibkr-market-bars-{n:03d}.txt"
        path = output_dir / filename
        path.write_text(value, encoding="ascii")
        os.chmod(path, 0o600)
        chunks.append({
            "path": f"rendezvous/returns/{run_id}/{filename}",
            "local_name": filename,
            "sha256": hashlib.sha256(value.encode("ascii")).hexdigest(),
            "chars": len(value),
        })
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "run_id": str(run_id),
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_pub).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "compression": "zlib",
        "chunks": chunks,
    }
    envelope_path = output_dir / "ibkr-warm-read-envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(envelope_path, 0o600)
    return envelope


def main() -> None:
    ap = argparse.ArgumentParser()
    for arg in ("handoff-file", "bars-file", "run-id", "public-head",
                "recipient-b64", "recipient-key-id", "output-dir"):
        ap.add_argument("--" + arg, required=True)
    args = ap.parse_args()
    payload = build_payload(
        handoff=_object(Path(args.handoff_file)), rows=_read_rows(Path(args.bars_file)),
        run_id=args.run_id, public_head=args.public_head,
    )
    envelope = encrypt_payload(
        payload=payload, recipient_b64=args.recipient_b64,
        recipient_key_id=args.recipient_key_id, run_id=args.run_id,
        output_dir=Path(args.output_dir),
    )
    print("IBKR_PRIVATE_BARS_ENCRYPTED=" + json.dumps({
        "schema": "mmibkr.ibkr_private_bars_receipt.v1",
        "run_id": str(args.run_id), "row_count": payload["row_count"],
        "contract_count": len(payload["contracts"]),
        "ciphertext_sha256": envelope["ciphertext_sha256"],
        "plaintext_published": False,
        "broker_mutation_authority": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
