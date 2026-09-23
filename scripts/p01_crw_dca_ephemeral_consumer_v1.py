from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

TRANSPORT_SCHEMA = "p01-crw-dca-ephemeral-x25519-v1"
HARNESS = "p01_crw_dca_adapter_v1"
PAYLOAD_CONTRACT = "p01-crw-dca-private-execution-contract-v1"
SOURCE_IDENTITY_SCHEMA = "p01-crw-dca-mm-source-identity-v1"
EXPECTED_SOURCE_REPOSITORY = "XoticHaze/mm-IBKR"
EXPECTED_SOURCE_COMMIT = "a083efc5755902315420200b7e341c8a1c9f2934"
EXPECTED_WORKLOAD_BLOB_SHA1 = "df215b2b6c8bc0ba2b6652e010862e789dbe2c4c"
EXPECTED_CORPUS_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
EXPECTED_CORPUS_BYTES = 18_026_715
WORKLOAD_REL = Path("scripts/operator/crw_backtest_summary_13z.py")
SOURCE_ROOT = "mm-IBKR"
SEED_FILE = "w96_seed_request.json"
CORPUS_FILE = "mnq-strategy-backtest-12min.csv"
CONTRACT_FILE = "p01_crw_dca_execution_contract.json"
SOURCE_IDENTITY_FILE = "p01_crw_dca_source_identity.json"


def _json(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise SystemExit(f"expected JSON object: {path.name}")
    return node


def _git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def _safe_extract(raw_zip: bytes, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        names = archive.namelist()
        if not names:
            raise SystemExit("private payload zip is empty")
        for info in archive.infolist():
            rel = Path(info.filename)
            if rel.is_absolute() or ".." in rel.parts:
                raise SystemExit("unsafe private payload path")
            target = (root / rel).resolve()
            if target != root and root not in target.parents:
                raise SystemExit("private payload escapes extraction root")
        archive.extractall(root)


def _validate_payload(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    required = [
        root / SOURCE_ROOT / WORKLOAD_REL,
        root / SEED_FILE,
        root / CORPUS_FILE,
        root / CONTRACT_FILE,
        root / SOURCE_IDENTITY_FILE,
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        raise SystemExit("private payload missing required paths: " + ",".join(missing))

    contract = _json(root / CONTRACT_FILE)
    if contract.get("schema") != PAYLOAD_CONTRACT or contract.get("authority") != "research_only":
        raise SystemExit("private execution contract mismatch")
    if contract.get("seed_id") != "W96":
        raise SystemExit("unexpected seed identity")
    try:
        capital = float(contract.get("capital_basis"))
    except Exception as exc:
        raise SystemExit("capital_basis missing or invalid") from exc
    if capital <= 0:
        raise SystemExit("capital_basis must be positive")
    if not str(contract.get("research_foundry_ref") or "").strip():
        raise SystemExit("research-foundry lineage missing")
    if not str(contract.get("corpus_source_id") or "").strip():
        raise SystemExit("governed corpus source identity missing")

    source = _json(root / SOURCE_IDENTITY_FILE)
    expected = {
        "schema": SOURCE_IDENTITY_SCHEMA,
        "repository": EXPECTED_SOURCE_REPOSITORY,
        "commit": EXPECTED_SOURCE_COMMIT,
        "canonical_workload_blob_sha1": EXPECTED_WORKLOAD_BLOB_SHA1,
    }
    for key, value in expected.items():
        if source.get(key) != value:
            raise SystemExit(f"MM source identity mismatch: {key}")
    observed_blob = _git_blob_sha1(root / SOURCE_ROOT / WORKLOAD_REL)
    if observed_blob != EXPECTED_WORKLOAD_BLOB_SHA1:
        raise SystemExit("canonical workload blob mismatch")
    return contract, source


def _adapter_receipt(root: Path, capital_basis: float) -> tuple[dict[str, Any], str]:
    adapter = Path(__file__).with_name("p01_crw_dca_adapter_consumer_v1.py")
    command = [
        sys.executable,
        str(adapter),
        "--payload-dir",
        str(root),
        "--source-root",
        SOURCE_ROOT,
        "--seed-request",
        SEED_FILE,
        "--corpus",
        CORPUS_FILE,
        "--expected-corpus-sha256",
        EXPECTED_CORPUS_SHA256,
        "--expected-corpus-bytes",
        str(EXPECTED_CORPUS_BYTES),
        "--capital-basis",
        str(capital_basis),
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    receipt: dict[str, Any] | None = None
    inner_sha = ""
    for line in completed.stdout.splitlines():
        if line.startswith("P01_CRW_DCA_ADAPTER_RECEIPT="):
            receipt = json.loads(line.split("=", 1)[1])
        elif line.startswith("P01_CRW_DCA_ADAPTER_RECEIPT_SHA256="):
            inner_sha = line.split("=", 1)[1].strip()
    if not isinstance(receipt, dict) or len(inner_sha) != 64:
        raise SystemExit("adapter did not emit deterministic receipt")
    return receipt, inner_sha


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    args = p.parse_args()

    envelope = _json(Path(args.envelope))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=TRANSPORT_SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )

    with tempfile.TemporaryDirectory(prefix="p01-crw-dca-") as tmp:
        root = Path(tmp)
        _safe_extract(plaintext, root)
        contract, source = _validate_payload(root)
        adapter_receipt, inner_sha = _adapter_receipt(root, float(contract["capital_basis"]))

    receipt = dict(adapter_receipt)
    receipt["public_harness"] = HARNESS
    receipt["transport_schema"] = TRANSPORT_SCHEMA
    receipt["public_provenance"] = {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "head_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
    }
    receipt["source_identity"] = {
        "repository": source["repository"],
        "commit": source["commit"],
        "canonical_workload_blob_sha1": source["canonical_workload_blob_sha1"],
    }
    receipt["governed_corpus_lineage"] = {
        "research_foundry_ref": contract["research_foundry_ref"],
        "corpus_source_id": contract["corpus_source_id"],
    }
    receipt["seed_id"] = contract["seed_id"]
    receipt["adapter_receipt_sha256"] = inner_sha
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    print("P01_CRW_DCA_PUBLIC_RECEIPT=" + encoded)
    print("P01_CRW_DCA_PUBLIC_RECEIPT_SHA256=" + hashlib.sha256(encoded.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
