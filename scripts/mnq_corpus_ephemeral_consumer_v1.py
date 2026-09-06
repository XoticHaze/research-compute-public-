from __future__ import annotations

"""Fixed sanitized consumer for the admitted private MNQ replay artifact.

This is a route/data-plane proof only. It does not execute a strategy, expose bars,
change StrategySpec/runtime state, submit orders or carry promotion authority.
"""

import argparse
import csv
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext, sha256_bytes

SCHEMA = "mnq-corpus-ephemeral-x25519-v1"
HARNESS = "mnq_replay_identity_probe_v1"
ARCHIVE_SHA256 = "86aae162c38354a0beb0abfc857f317f596a07c9e317d4d21e4fb799881c2b2e"
DATASET_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
ROWS = 192553
FIRST = "2019-05-05T22:00:00+00:00"
LAST = "2026-02-19T02:12:00+00:00"
EXPECTED_FILES = {
    "output/manifest.json",
    "output/mnq-strategy-backtest-12min.csv",
    "output/roll_schedule.csv",
    "supplement-receipt.json",
    "publication.log",
}


def _validate_zip(payload: bytes) -> dict:
    if sha256_bytes(payload) != ARCHIVE_SHA256:
        raise RuntimeError("MNQ artifact archive digest mismatch")
    with tempfile.TemporaryDirectory(prefix="mnq-corpus-private-") as td:
        root = Path(td)
        archive = root / "payload.zip"
        archive.write_bytes(payload)
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            if names != EXPECTED_FILES:
                raise RuntimeError(f"MNQ artifact file set mismatch: {sorted(names)}")
            for info in zf.infolist():
                if info.is_dir():
                    raise RuntimeError("directory member rejected")
                target = (root / info.filename).resolve()
                if root.resolve() not in target.parents:
                    raise RuntimeError("zip path traversal rejected")

            manifest = json.loads(zf.read("output/manifest.json").decode("utf-8"))
            if manifest.get("schema") != "foundry.strategy_backtest_ohlc.v1":
                raise RuntimeError("MNQ manifest schema mismatch")
            if manifest.get("data_role") != "STRATEGY_BACKTEST_OHLC":
                raise RuntimeError("MNQ data role mismatch")
            if manifest.get("canonical_scope") != "research_strategy_replay_only":
                raise RuntimeError("MNQ canonical scope mismatch")
            if manifest.get("symbol") != "MNQ" or manifest.get("timeframe") != "12Min":
                raise RuntimeError("MNQ symbol/timeframe mismatch")
            authority = manifest.get("authority") or {}
            if authority.get("research_only") is not True:
                raise RuntimeError("MNQ research-only boundary missing")
            for key in ("promotion_authority", "strategy_spec_write", "runtime_activation", "broker_submit"):
                if authority.get(key) is not False:
                    raise RuntimeError(f"MNQ authority boundary failed: {key}")

            node = manifest.get("dataset") or {}
            if (
                node.get("sha256") != DATASET_SHA256
                or int(node.get("rows", -1)) != ROWS
                or node.get("first_timestamp") != FIRST
                or node.get("last_timestamp") != LAST
            ):
                raise RuntimeError("MNQ manifest dataset identity mismatch")

            csv_bytes = zf.read("output/mnq-strategy-backtest-12min.csv")
            if hashlib.sha256(csv_bytes).hexdigest() != DATASET_SHA256:
                raise RuntimeError("MNQ CSV digest mismatch")
            reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
            count = 0
            first = None
            last = None
            for row in reader:
                ts = str(row.get("timestamp") or "")
                if first is None:
                    first = ts
                last = ts
                count += 1
            if count != ROWS or first != FIRST or last != LAST:
                raise RuntimeError("MNQ CSV row/timestamp identity mismatch")

    return {
        "schema": "mnq-corpus-ephemeral-receipt-v1",
        "authority": "research_only",
        "harness": HARNESS,
        "artifact_archive_sha256": ARCHIVE_SHA256,
        "dataset_sha256": DATASET_SHA256,
        "rows": ROWS,
        "first_timestamp": FIRST,
        "last_timestamp": LAST,
        "data_role": "STRATEGY_BACKTEST_OHLC",
        "promotion_authority": False,
        "strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "live_trading_change": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    args = p.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    ciphertext = Path(args.ciphertext).read_bytes()
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=ciphertext,
        private_key_path=Path(args.private_key),
        expected_schema=SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )
    receipt = _validate_zip(plaintext)
    print("MNQ_CORPUS_EPHEMERAL_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
