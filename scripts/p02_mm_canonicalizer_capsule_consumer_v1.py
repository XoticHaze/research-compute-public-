from __future__ import annotations

"""Fail-closed public consumer for the private MM P02 canonicalizer source capsule."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "p02-mm-canonicalizer-capsule-v1"
HARNESS = "p02_mm_canonicalize_admitted_mnq_v1"
EXPECTED_MM_COMMIT = "fd81406cec3860fb6f6452c8a3c2f638ee1ccfde"
EXPECTED_SOURCE_SHA = "d99dba176d2a474b8f2a66d6f43bd62d49ab70237d92e4f2a573246ae744fcc0"
EXPECTED_UNION = "81a1b9a40ab62c41b42dc72e7d5d5b7b58d0d71a0bdd7b02d736c20de095b2bd"
ENTRYPOINT = "scripts/operator/materialize_admitted_futures_source_canonical.py"
EXPECTED_FILES = {
    ENTRYPOINT,
    "scripts/operator/publish_canonical_feature_sidecar.py",
    "feature_contract.py",
    "futures_manager.py",
    "timeframe_adapters.py",
    "indicators.py",
    "indicators_registry.py",
    "futures_contract_registry.py",
    "futures_product_registry.py",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_extract(blob: bytes, root: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        for member in tf.getmembers():
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or member.issym() or member.islnk():
                raise RuntimeError("unsafe P02 canonicalizer capsule member")
        tf.extractall(root)


def _validate(root: Path) -> dict:
    manifest = json.loads((root / "payload_manifest.json").read_text())
    required = {"schema", "mm_commit", "entrypoint", "symbol", "source_timeframe", "target_timeframe", "expected_source_sha256", "expected_union_fingerprint", "files"}
    if set(manifest) != required or manifest["schema"] != SCHEMA:
        raise RuntimeError("P02 canonicalizer manifest contract mismatch")
    if manifest["mm_commit"] != EXPECTED_MM_COMMIT or manifest["entrypoint"] != ENTRYPOINT:
        raise RuntimeError("P02 canonicalizer MM identity mismatch")
    if manifest["symbol"] != "MNQ" or manifest["source_timeframe"] != "1Min" or manifest["target_timeframe"] != "12Min":
        raise RuntimeError("P02 canonicalizer symbol/timeframe mismatch")
    if manifest["expected_source_sha256"] != EXPECTED_SOURCE_SHA or manifest["expected_union_fingerprint"] != EXPECTED_UNION:
        raise RuntimeError("P02 canonicalizer admitted-source identity mismatch")
    files = manifest["files"]
    if set(files) != EXPECTED_FILES:
        raise RuntimeError("P02 canonicalizer private file set mismatch")
    for rel, expected in files.items():
        if _sha((root / rel).read_bytes()) != expected:
            raise RuntimeError("P02 canonicalizer file digest mismatch: " + rel)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--envelope", required=True)
    ap.add_argument("--ciphertext", required=True)
    ap.add_argument("--private-key", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--response-root", required=True)
    ap.add_argument("--source-csv", required=True)
    ap.add_argument("--source-lineage", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--receipt", required=True)
    args = ap.parse_args()

    envelope = json.loads(Path(args.envelope).read_text())
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope, ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key), expected_schema=SCHEMA,
        expected_run_id=args.run_id, expected_harness=HARNESS,
        response_root=args.response_root,
    )
    source = Path(args.source_csv)
    lineage_path = Path(args.source_lineage)
    if _sha(source.read_bytes()) != EXPECTED_SOURCE_SHA:
        raise RuntimeError("P02 admitted source byte identity mismatch")
    lineage = json.loads(lineage_path.read_text())
    if lineage.get("source_sha256") != EXPECTED_SOURCE_SHA or lineage.get("union_fingerprint_sha256") != EXPECTED_UNION:
        raise RuntimeError("P02 admitted lineage identity mismatch")
    if lineage.get("coverage_qualified") is not True:
        raise RuntimeError("P02 admitted source is not coverage-qualified")

    with tempfile.TemporaryDirectory(prefix="p02-mm-canonicalizer-") as td:
        root = Path(td)
        _safe_extract(plaintext, root)
        manifest = _validate(root)
        data_root = Path(args.data_root).resolve()
        receipt = Path(args.receipt).resolve()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root)
        subprocess.run([
            "python", str(root / ENTRYPOINT),
            "--source-csv", str(source.resolve()),
            "--source-lineage-json", str(lineage_path.resolve()),
            "--expected-source-sha256", EXPECTED_SOURCE_SHA,
            "--data-root", str(data_root), "--root", "MNQ",
            "--source-timeframe", "1Min", "--target-timeframe", "12Min",
            "--receipt-json", str(receipt),
        ], cwd=root, env=env, check=True)

    result = json.loads(Path(args.receipt).read_text())
    if result.get("schema") != "mm.admitted_futures_source_canonical_materialization.v1" or result.get("status") != "PASS":
        raise RuntimeError("P02 canonical materialization receipt mismatch")
    for key in ("strategy_spec_mutation", "runtime_authority_change", "broker_submission", "live_trading_change"):
        if result.get("safety", {}).get(key) is not False:
            raise RuntimeError("P02 canonicalizer safety contract mismatch: " + key)
    print(json.dumps({
        "schema": "p02-public-canonicalizer-receipt-v1",
        "run_id": str(args.run_id), "mm_commit": manifest["mm_commit"],
        "source_sha256": result.get("source_sha256"), "source_rows": result.get("source_rows"),
        "target_rows": result.get("target_rows"), "raw_sha256": result.get("raw_sha256"),
        "features_sha256": result.get("features_sha256"),
        "feature_manifest_hash": result.get("feature_manifest_hash"),
        "feature_semantic_hash": result.get("feature_semantic_hash"),
        "sidecar_status": result.get("sidecar", {}).get("status"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
