from __future__ import annotations

"""Fail-closed public-plane binding for the first real P02 Model Lab consumer.

The encrypted plaintext is a tar archive. This wrapper validates a fixed manifest
before executing the private MM consumer. It emits no private payload contents.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "p02-model-lab-xgboost-capsule-v1"
HARNESS = "p02_model_lab_xgboost_first_consumer_v1"
EXPECTED_MM_COMMIT = "fc8890d5f62a983549d5d3760aa6ba9723578262"
EXPECTED_ENTRYPOINT = "scripts/operator/model_lab_xgboost_first_consumer.py"
EXPECTED_SYMBOL = "MNQ"
EXPECTED_TIMEFRAME = "12Min"
MANIFEST_FIELDS = {
    "schema", "mm_commit", "entrypoint", "symbol", "timeframe",
    "data_identity", "files"
}


def _safe_extract(blob: bytes, root: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        members = tf.getmembers()
        for member in members:
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or member.issym() or member.islnk():
                raise RuntimeError("unsafe capsule member")
        tf.extractall(root)


def _validate(root: Path) -> dict:
    manifest = json.loads((root / "payload_manifest.json").read_text())
    if set(manifest) != MANIFEST_FIELDS or manifest["schema"] != SCHEMA:
        raise RuntimeError("P02 manifest contract mismatch")
    if manifest["mm_commit"] != EXPECTED_MM_COMMIT:
        raise RuntimeError("P02 MM commit mismatch")
    if manifest["entrypoint"] != EXPECTED_ENTRYPOINT:
        raise RuntimeError("P02 entrypoint mismatch")
    if manifest["symbol"] != EXPECTED_SYMBOL or manifest["timeframe"] != EXPECTED_TIMEFRAME:
        raise RuntimeError("P02 symbol/timeframe mismatch")
    files = manifest["files"]
    if not isinstance(files, dict) or not files or EXPECTED_ENTRYPOINT not in files:
        raise RuntimeError("P02 file identity map missing")
    for rel, expected in files.items():
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            raise RuntimeError("P02 file path invalid")
        raw = (root / p).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError("P02 file digest mismatch: " + rel)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--envelope", required=True)
    ap.add_argument("--ciphertext", required=True)
    ap.add_argument("--private-key", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--response-root", required=True)
    args = ap.parse_args()
    envelope = json.loads(Path(args.envelope).read_text())
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )
    with tempfile.TemporaryDirectory(prefix="p02-model-lab-") as td:
        root = Path(td)
        manifest = _validate(root) if False else None
        _safe_extract(plaintext, root)
        manifest = _validate(root)
        data_root = root / "data_root"
        if not data_root.is_dir():
            raise RuntimeError("P02 canonical data_root missing")
        out = root / "sanitized_receipt.json"
        cmd = [
            "python", str(root / EXPECTED_ENTRYPOINT),
            "--data-root", str(data_root), "--asset-type", "futures",
            "--symbol", EXPECTED_SYMBOL, "--timeframe", EXPECTED_TIMEFRAME,
            "--horizon-bars", "5", "--start-year", "2022",
            "--test-span-years", "1", "--min-test-rows", "200",
            "--output", str(out),
        ]
        subprocess.run(cmd, cwd=root, check=True)
        receipt = json.loads(out.read_text())
        if receipt.get("schema") != "mm.model_lab_xgboost_first_consumer.v1":
            raise RuntimeError("P02 receipt schema mismatch")
        print(json.dumps({
            "schema": "p02-public-consumer-receipt-v1",
            "run_id": str(args.run_id),
            "mm_commit": manifest["mm_commit"],
            "data_identity": manifest["data_identity"],
            "symbol": receipt.get("symbol"),
            "timeframe": receipt.get("timeframe"),
            "matched_window": receipt.get("matched_window"),
            "incremental_predictive_value": receipt.get("incremental_predictive_value"),
            "economic_evidence": receipt.get("economic_evidence"),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
