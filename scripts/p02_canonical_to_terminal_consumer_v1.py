from __future__ import annotations

"""Fail-closed public P02 canonicalization -> first-consumer binding.

The public job receives already-admitted MNQ 1Min source bytes from the registered
public artifact and an encrypted source-only MM capsule. The decrypted MM source is
used only inside the runner temporary directory to invoke the owning canonical
resampler/indicator/writer/sidecar path and then the first Model Lab consumer.
Only a sanitized receipt is emitted.
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

SCHEMA = "p02-canonical-to-terminal-source-capsule-v1"
HARNESS = "p02_canonical_to_terminal_v1"
EXPECTED_MM_COMMIT = "fd81406cec3860fb6f6452c8a3c2f638ee1ccfde"
EXPECTED_SOURCE_SHA256 = "d99dba176d2a474b8f2a66d6f43bd62d49ab70237d92e4f2a573246ae744fcc0"
EXPECTED_UNION_FINGERPRINT = "81a1b9a40ab62c41b42dc72e7d5d5b7b58d0d71a0bdd7b02d736c20de095b2bd"
EXPECTED_SOURCE_AUTHORITY = "XoticHaze/research-foundry#78"
CANONICAL_ENTRYPOINT = "scripts/operator/materialize_admitted_futures_source_canonical.py"
TERMINAL_ENTRYPOINT = "scripts/operator/model_lab_xgboost_first_consumer.py"
EXPECTED_SYMBOL = "MNQ"
EXPECTED_SOURCE_TIMEFRAME = "1Min"
EXPECTED_TARGET_TIMEFRAME = "12Min"
MANIFEST_FIELDS = {
    "schema",
    "mm_commit",
    "canonical_entrypoint",
    "terminal_entrypoint",
    "symbol",
    "source_timeframe",
    "target_timeframe",
    "files",
}


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(blob: bytes, root: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        members = tf.getmembers()
        if not members:
            raise RuntimeError("P02 source capsule is empty")
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise RuntimeError("unsafe P02 source capsule member")
        tf.extractall(root)


def _validate_source_capsule(root: Path) -> dict:
    manifest_path = root / "payload_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("P02 source capsule manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise RuntimeError("P02 source capsule manifest field mismatch")
    expected = {
        "schema": SCHEMA,
        "mm_commit": EXPECTED_MM_COMMIT,
        "canonical_entrypoint": CANONICAL_ENTRYPOINT,
        "terminal_entrypoint": TERMINAL_ENTRYPOINT,
        "symbol": EXPECTED_SYMBOL,
        "source_timeframe": EXPECTED_SOURCE_TIMEFRAME,
        "target_timeframe": EXPECTED_TARGET_TIMEFRAME,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"P02 source capsule {key} mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("P02 source capsule identity map missing")
    for required in (CANONICAL_ENTRYPOINT, TERMINAL_ENTRYPOINT, "feature_contract.py", "futures_manager.py"):
        if required not in files:
            raise RuntimeError(f"P02 source capsule missing required identity: {required}")
    for rel, expected_sha in files.items():
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise RuntimeError("P02 source capsule path invalid")
        node = root / rel_path
        if not node.is_file() or _sha256_path(node) != expected_sha:
            raise RuntimeError(f"P02 source capsule file identity mismatch: {rel}")
    return manifest


def _validate_admitted_source(source_csv: Path, lineage_json: Path) -> dict:
    if not source_csv.is_file() or not lineage_json.is_file():
        raise RuntimeError("P02 admitted source artifact is incomplete")
    actual_sha = _sha256_path(source_csv)
    if actual_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"P02 admitted source SHA mismatch: {actual_sha}")
    lineage = json.loads(lineage_json.read_text(encoding="utf-8"))
    if lineage.get("source_sha256") != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("P02 admitted source lineage SHA mismatch")
    if lineage.get("union_fingerprint_sha256") != EXPECTED_UNION_FINGERPRINT:
        raise RuntimeError("P02 admitted source union fingerprint mismatch")
    if lineage.get("authority") != EXPECTED_SOURCE_AUTHORITY:
        raise RuntimeError("P02 admitted source authority mismatch")
    if lineage.get("coverage_qualified") is not True:
        raise RuntimeError("P02 admitted source is not coverage-qualified")
    if lineage.get("full_calendar_complete") is not False:
        raise RuntimeError("P02 source completeness contract drift")
    return lineage


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--ciphertext", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--response-root", required=True)
    parser.add_argument("--source-csv", required=True)
    parser.add_argument("--source-lineage-json", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_csv = Path(args.source_csv).resolve()
    lineage_json = Path(args.source_lineage_json).resolve()
    lineage = _validate_admitted_source(source_csv, lineage_json)

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

    with tempfile.TemporaryDirectory(prefix="p02-canonical-terminal-") as td:
        root = Path(td)
        private_src = root / "mm_source"
        private_src.mkdir()
        _safe_extract(plaintext, private_src)
        manifest = _validate_source_capsule(private_src)

        data_root = root / "data_root"
        canonical_receipt_path = root / "canonical_receipt.json"
        _run(
            [
                "python",
                str(private_src / CANONICAL_ENTRYPOINT),
                "--source-csv",
                str(source_csv),
                "--source-lineage-json",
                str(lineage_json),
                "--expected-source-sha256",
                EXPECTED_SOURCE_SHA256,
                "--data-root",
                str(data_root),
                "--root",
                EXPECTED_SYMBOL,
                "--source-timeframe",
                EXPECTED_SOURCE_TIMEFRAME,
                "--target-timeframe",
                EXPECTED_TARGET_TIMEFRAME,
                "--receipt-json",
                str(canonical_receipt_path),
            ],
            cwd=private_src,
        )
        canonical = json.loads(canonical_receipt_path.read_text(encoding="utf-8"))
        if canonical.get("schema") != "mm.admitted_futures_source_canonical_materialization.v1":
            raise RuntimeError("P02 canonical receipt schema mismatch")
        if canonical.get("status") != "PASS":
            raise RuntimeError("P02 canonical materialization did not pass")
        if canonical.get("source_sha256") != EXPECTED_SOURCE_SHA256:
            raise RuntimeError("P02 canonical receipt source identity mismatch")
        if canonical.get("root") != EXPECTED_SYMBOL or canonical.get("target_timeframe") != EXPECTED_TARGET_TIMEFRAME:
            raise RuntimeError("P02 canonical receipt symbol/timeframe mismatch")
        safety = canonical.get("safety") or {}
        forbidden_true = (
            "new_downloader",
            "new_resampler",
            "new_indicator_engine",
            "new_feature_schema",
            "network_ib_calls",
            "strategy_spec_mutation",
            "runtime_authority_change",
            "broker_submission",
            "live_trading_change",
        )
        if any(bool(safety.get(key)) for key in forbidden_true):
            raise RuntimeError("P02 canonical materialization crossed a protected boundary")
        feature_path = Path(str(canonical.get("features_path") or ""))
        sidecar = canonical.get("sidecar") or {}
        if not feature_path.is_file() or _sha256_path(feature_path) != canonical.get("features_sha256"):
            raise RuntimeError("P02 canonical feature identity verification failed")
        if not canonical.get("feature_manifest_hash") or not canonical.get("feature_semantic_hash"):
            raise RuntimeError("P02 canonical feature manifest identity missing")
        if not isinstance(sidecar, dict) or not sidecar:
            raise RuntimeError("P02 canonical causal sidecar receipt missing")

        terminal_receipt_path = root / "terminal_receipt.json"
        _run(
            [
                "python",
                str(private_src / TERMINAL_ENTRYPOINT),
                "--data-root",
                str(data_root),
                "--asset-type",
                "futures",
                "--symbol",
                EXPECTED_SYMBOL,
                "--timeframe",
                EXPECTED_TARGET_TIMEFRAME,
                "--horizon-bars",
                "5",
                "--start-year",
                "2022",
                "--test-span-years",
                "1",
                "--min-test-rows",
                "200",
                "--output",
                str(terminal_receipt_path),
            ],
            cwd=private_src,
        )
        terminal = json.loads(terminal_receipt_path.read_text(encoding="utf-8"))
        if terminal.get("schema") != "mm.model_lab_xgboost_first_consumer.v1":
            raise RuntimeError("P02 terminal consumer receipt schema mismatch")

        sanitized = {
            "schema": "p02-canonical-to-terminal-public-receipt-v1",
            "status": "PASS",
            "run_id": str(args.run_id),
            "mm_commit": manifest["mm_commit"],
            "source": {
                "authority": lineage.get("authority"),
                "source_sha256": EXPECTED_SOURCE_SHA256,
                "union_fingerprint_sha256": EXPECTED_UNION_FINGERPRINT,
                "rows": lineage.get("rows"),
                "first_timestamp": lineage.get("first_timestamp"),
                "last_timestamp": lineage.get("last_timestamp"),
                "known_material_gaps": lineage.get("known_material_gaps"),
            },
            "canonical": {
                "target_timeframe": canonical.get("target_timeframe"),
                "source_rows": canonical.get("source_rows"),
                "target_rows": canonical.get("target_rows"),
                "raw_sha256": canonical.get("raw_sha256"),
                "features_sha256": canonical.get("features_sha256"),
                "feature_manifest_hash": canonical.get("feature_manifest_hash"),
                "feature_semantic_hash": canonical.get("feature_semantic_hash"),
                "sidecar_status": sidecar.get("status", "PRESENT"),
            },
            "terminal_consumer": {
                "symbol": terminal.get("symbol"),
                "timeframe": terminal.get("timeframe"),
                "target_identity": terminal.get("target_identity"),
                "matched_window": terminal.get("matched_window"),
                "incremental_predictive_value": terminal.get("incremental_predictive_value"),
                "economic_evidence": terminal.get("economic_evidence"),
            },
            "safety": {
                "decrypted_private_source_ephemeral": True,
                "canonical_feature_bytes_published": False,
                "runtime_authority_change": False,
                "strategy_spec_authority": False,
                "promotion_authority": False,
                "broker_submission": False,
                "live_trading_change": False,
            },
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(sanitized, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(sanitized, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
