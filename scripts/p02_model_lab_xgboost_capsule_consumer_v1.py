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

# Exact inventory emitted by the pinned private MM packager at fc8890d5.
# Archive paths are fixed independent of the caller-authored manifest.
EXPECTED_SOURCE_FILES = frozenset({
    EXPECTED_ENTRYPOINT,
    "model_lab_training_matrix.py",
    "model_lab_canonical_data.py",
    "model_lab_xgboost.py",
    "model_lab_canonical_trainer.py",
    "model_lab_validation.py",
    "predictive_target_spec.py",
    "feature_contract.py",
    "timeframe_adapters.py",
})
EXPECTED_DATA_FILES = {
    "raw_sha256": "data_root/futures/MNQ-CONTINUOUS/12Min.csv",
    "features_sha256": "data_root/futures/MNQ-CONTINUOUS/12Min.features.csv",
    "sidecar_sha256": "data_root/futures/MNQ-CONTINUOUS/12Min.features.csv.manifest.json",
}
EXPECTED_DATA_IDENTITY_FIELDS = frozenset({
    *EXPECTED_DATA_FILES, "feature_manifest_hash", "feature_semantic_hash",
})
EXPECTED_ARCHIVE_FILES = frozenset({
    "payload_manifest.json", *EXPECTED_SOURCE_FILES, *EXPECTED_DATA_FILES.values(),
})


def _safe_extract(blob: bytes, root: Path) -> None:
    """Accept only the pinned packager's exact regular-file inventory."""
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        members = tf.getmembers()
        if len(members) != len(EXPECTED_ARCHIVE_FILES):
            raise RuntimeError("P02 capsule archive member count mismatch")
        seen: set[str] = set()
        for member in members:
            name = member.name
            if name not in EXPECTED_ARCHIVE_FILES or name in seen or not member.isfile():
                raise RuntimeError("P02 capsule archive member inventory mismatch")
            seen.add(name)
        if seen != EXPECTED_ARCHIVE_FILES:
            raise RuntimeError("P02 capsule archive member inventory incomplete")
        # Explicit regular-file writes avoid extractall's platform-dependent
        # special-member handling and never follow archive-provided links.
        for member in members:
            stream = tf.extractfile(member)
            if stream is None:
                raise RuntimeError("P02 capsule archive regular member unreadable")
            node = root / member.name
            node.parent.mkdir(parents=True, exist_ok=True)
            node.write_bytes(stream.read())


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
    if not isinstance(files, dict) or set(files) != EXPECTED_SOURCE_FILES:
        raise RuntimeError("P02 source file identity map mismatch")
    for rel, expected in files.items():
        raw = (root / rel).read_bytes()
        if not isinstance(expected, str) or hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError("P02 file digest mismatch: " + rel)
    data_identity = manifest["data_identity"]
    if not isinstance(data_identity, dict) or set(data_identity) != EXPECTED_DATA_IDENTITY_FIELDS:
        raise RuntimeError("P02 data identity map mismatch")
    for key, rel in EXPECTED_DATA_FILES.items():
        expected = data_identity[key]
        raw = (root / rel).read_bytes()
        if not isinstance(expected, str) or hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError("P02 data digest mismatch: " + key)
    return manifest



def _run_private_consumer(cmd: list[str], root: Path) -> None:
    """Do not forward the private consumer's full JSON or error text to public logs."""
    completed = subprocess.run(
        cmd,
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("P02 private consumer failed; output withheld")



# Minimum public receipt while no independently approved P02 result-field
# classification or authenticated private full-result return is available.
PUBLIC_RECEIPT_FIELDS = frozenset({
    "schema", "run_id", "mm_commit", "symbol", "timeframe", "status",
})


def _public_receipt_projection(run_id: str, manifest: dict) -> dict:
    result = {
        "schema": "p02-public-consumer-receipt-v1",
        "run_id": str(run_id),
        "mm_commit": EXPECTED_MM_COMMIT,
        "symbol": EXPECTED_SYMBOL,
        "timeframe": EXPECTED_TIMEFRAME,
        "status": "PRIVATE_RESULT_WITHHELD_PENDING_TWO_SIDED_ADMISSION",
    }
    if set(result) != PUBLIC_RECEIPT_FIELDS:
        raise RuntimeError("P02 public receipt field contract mismatch")
    return result


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
        _run_private_consumer(cmd, root)
        receipt = json.loads(out.read_text())
        if receipt.get("schema") != "mm.model_lab_xgboost_first_consumer.v1":
            raise RuntimeError("P02 receipt schema mismatch")
        print(json.dumps(_public_receipt_projection(args.run_id, manifest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
