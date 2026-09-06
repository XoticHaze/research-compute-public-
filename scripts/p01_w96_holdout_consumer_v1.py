from __future__ import annotations

"""Fixed research-only admission shell for the P01 W96 fresh holdout.

This module intentionally does not implement a new trading evaluator. It admits a
private payload only when it contains the exact frozen scientific contract and a
consumer bundle supplied by private authority, then executes that bundle in the
public runner. The private bundle must emit one JSON receipt line prefixed with
P01_W96_HOLDOUT_RECEIPT=. This keeps transport and workload authority separate.
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "p01-w96-holdout-ephemeral-x25519-v1"
HARNESS = "p01_w96_entry_holdout_v1"
AUTHORITY = "research_only"
EXPECTED_CONTRACT = {
    "symbol": "MNQ",
    "timeframe": "12Min",
    "holdout_start_exclusive": "2026-02-19T02:12:00Z",
    "incumbent": {"window": 96, "entry_extreme": -2.8, "exit_extreme": 4.5},
    "challenger": {"window": 96, "entry_extreme": -2.52, "exit_extreme": 4.5},
    "frozen_equal_semantics": ["dca", "costs", "execution", "roll", "warmup"],
}
REQUIRED_RECEIPT_KEYS = {
    "schema", "authority", "symbol", "timeframe", "holdout_start_exclusive",
    "holdout_end", "incumbent", "challenger", "delta", "decision",
    "strategy_spec_write", "runtime_activation", "broker_submit",
    "promotion_authority", "live_trading_change",
}


def _load_payload(raw: bytes) -> dict:
    node = json.loads(raw.decode("utf-8"))
    if not isinstance(node, dict) or set(node) != {"schema", "authority", "contract", "consumer_source", "data_b64"}:
        raise RuntimeError("P01 payload field set mismatch")
    if node["schema"] != "p01-w96-holdout-private-payload-v1" or node["authority"] != AUTHORITY:
        raise RuntimeError("P01 payload schema/authority mismatch")
    if node["contract"] != EXPECTED_CONTRACT:
        raise RuntimeError("P01 frozen scientific contract mismatch")
    if not isinstance(node["consumer_source"], str) or not node["consumer_source"].strip():
        raise RuntimeError("P01 consumer source missing")
    if not isinstance(node["data_b64"], str) or not node["data_b64"].strip():
        raise RuntimeError("P01 holdout data missing")
    return node


def _run_private_consumer(node: dict) -> dict:
    import base64
    with tempfile.TemporaryDirectory(prefix="p01-w96-") as td:
        root = Path(td)
        source = root / "consumer.py"
        data = root / "holdout.csv"
        source.write_text(node["consumer_source"], encoding="utf-8")
        data.write_bytes(base64.b64decode(node["data_b64"].encode("ascii"), validate=True))
        proc = subprocess.run(
            ["python", str(source), "--data", str(data)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=1200,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"private scientific consumer failed rc={proc.returncode}")
        prefix = "P01_W96_HOLDOUT_RECEIPT="
        lines = [line for line in proc.stdout.splitlines() if line.startswith(prefix)]
        if len(lines) != 1:
            raise RuntimeError("private scientific consumer did not emit exactly one receipt")
        receipt = json.loads(lines[0][len(prefix):])
    if not isinstance(receipt, dict) or set(receipt) != REQUIRED_RECEIPT_KEYS:
        raise RuntimeError("P01 receipt field set mismatch")
    if receipt["schema"] != "p01-w96-holdout-receipt-v1" or receipt["authority"] != AUTHORITY:
        raise RuntimeError("P01 receipt schema/authority mismatch")
    if receipt["symbol"] != "MNQ" or receipt["timeframe"] != "12Min":
        raise RuntimeError("P01 receipt symbol/timeframe mismatch")
    if receipt["holdout_start_exclusive"] != EXPECTED_CONTRACT["holdout_start_exclusive"]:
        raise RuntimeError("P01 receipt holdout boundary mismatch")
    for key in ("strategy_spec_write", "runtime_activation", "broker_submit", "promotion_authority", "live_trading_change"):
        if receipt[key] is not False:
            raise RuntimeError(f"P01 forbidden authority asserted: {key}")
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    args = p.parse_args()
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )
    receipt = _run_private_consumer(_load_payload(plaintext))
    print("P01_W96_HOLDOUT_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
