from __future__ import annotations

import argparse
import copy
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
EXPECTED_WORKLOAD_BLOB_SHA1 = "df215b2b6c8bc0ba2b6652e010862e789dbe2c4c"
EXPECTED_CORPUS_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
EXPECTED_CORPUS_BYTES = 18_026_715
WORKLOAD_REL = Path("scripts/operator/crw_backtest_summary_13z.py")
RUNTIME_REL = Path("config/selected_runtime_universe_14tu.json")
CORPUS_FILE = "mnq-strategy-backtest-12min.csv"
CONTRACT_FILE = "p01_crw_dca_execution_contract.json"
SEED_FILE = "w96_seed_request.json"
RUNTIME_ID = "crw_mnq_12m_proven_exec"


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
        if not archive.namelist():
            raise SystemExit("private payload zip is empty")
        for info in archive.infolist():
            rel = Path(info.filename)
            if rel.is_absolute() or ".." in rel.parts:
                raise SystemExit("unsafe private payload path")
            target = (root / rel).resolve()
            if target != root and root not in target.parents:
                raise SystemExit("private payload escapes extraction root")
        archive.extractall(root)


def _validate_foundry_payload(root: Path) -> dict[str, Any]:
    corpus = root / CORPUS_FILE
    contract_path = root / CONTRACT_FILE
    if not corpus.exists() or not contract_path.exists():
        raise SystemExit("Foundry payload missing corpus or execution contract")
    contract = _json(contract_path)
    if contract.get("schema") != PAYLOAD_CONTRACT or contract.get("authority") != "research_only":
        raise SystemExit("private execution contract mismatch")
    if contract.get("seed_id") != "W96":
        raise SystemExit("unexpected seed identity")
    if str(contract.get("dataset_sha256") or "") != EXPECTED_CORPUS_SHA256:
        raise SystemExit("execution contract dataset SHA mismatch")
    if int(contract.get("dataset_bytes") or 0) != EXPECTED_CORPUS_BYTES:
        raise SystemExit("execution contract dataset byte count mismatch")
    if not str(contract.get("research_foundry_ref") or "").strip():
        raise SystemExit("research-foundry lineage missing")
    if not str(contract.get("corpus_source_id") or "").strip():
        raise SystemExit("governed corpus source identity missing")
    observed_sha = hashlib.sha256(corpus.read_bytes()).hexdigest()
    observed_bytes = corpus.stat().st_size
    if observed_sha != EXPECTED_CORPUS_SHA256 or observed_bytes != EXPECTED_CORPUS_BYTES:
        raise SystemExit("governed corpus identity mismatch")
    return contract


def _validate_mm_source(source_root: Path, materialization_path: Path) -> dict[str, Any]:
    materialization = _json(materialization_path)
    if materialization.get("schema") != "mmibkr.cloud_source_materialization.v1" or materialization.get("ok") is not True:
        raise SystemExit("MM cloud source materialization contract mismatch")
    source_sha = str(materialization.get("source_sha") or "").lower()
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise SystemExit("MM source SHA missing")
    if str(materialization.get("source_ref") or "") != "main":
        raise SystemExit("P01 DCA requires canonical MM main source")
    workload = source_root / WORKLOAD_REL
    runtime = source_root / RUNTIME_REL
    if not workload.exists() or not runtime.exists():
        raise SystemExit("MM source closure missing canonical workload/runtime config")
    if _git_blob_sha1(workload) != EXPECTED_WORKLOAD_BLOB_SHA1:
        raise SystemExit("canonical CRW workload blob mismatch")
    return materialization


def _runtime_entry(source_root: Path) -> dict[str, Any]:
    runtime = _json(source_root / RUNTIME_REL)
    for node in runtime.get("runtime_ids") or []:
        if isinstance(node, dict) and node.get("runtime_id") == RUNTIME_ID:
            return node
    raise SystemExit(f"selected runtime {RUNTIME_ID} missing")


def _build_w96_seed(source_root: Path, corpus: Path) -> dict[str, Any]:
    node = _runtime_entry(source_root)
    strategy = copy.deepcopy(node.get("strategy_params") or {})
    policy = copy.deepcopy(node.get("execution_policy") or {})
    if not strategy or not policy:
        raise SystemExit("selected MNQ runtime lacks strategy/execution policy")
    if bool(strategy.get("ENABLE_DCA")) is not True or bool(policy.get("dca_enabled")) is not True:
        raise SystemExit("selected W96 source is not DCA-enabled")

    base_qty = int(policy.get("base_qty"))
    max_contracts = int(policy.get("max_contracts"))
    max_adds = int(policy.get("max_dca_adds"))
    if (base_qty, max_contracts, max_adds) != (1, 3, 2):
        raise SystemExit("selected MNQ DCA capital controls drifted from admitted W96")

    strategy.update(
        {
            "WINDOW": 96,
            "ENTRY_EXTREME": -2.52,
            "EXIT_EXTREME": 4.5,
            "entry_threshold": -2.52,
            "exit_threshold": 4.5,
            "ENABLE_DCA": True,
            "DCA_BASE_QTY": base_qty,
            "DCA_MAX_CONTRACTS": max_contracts,
            "DCA_MAX_ADDS": max_adds,
            "DCA_TRIGGER_MODE": "tiered_previous_buy",
            "DCA_TIER_DRAWDOWNS_PCT": [1, 2],
            # Accepted P01/W96 cost basis: 0.3 MNQ index points per contract-side.
            "commission_per_share": 0.3,
            "min_commission": 0.0,
            "spread_bps": 0.0,
            "slippage_bps": 2.5,
            "SLIPPAGE_BPS": 2.5,
        }
    )
    return {
        "strategy_id": "crw_score_multi_mode",
        "symbols": ["MNQ"],
        "timeframe": "12Min",
        "asset_type": "futures",
        "params": strategy,
        "_verified_source_paths": {"MNQ": str(corpus.resolve())},
        "paper_only": True,
        "live_allowed": False,
    }


def _adapter_receipt(root: Path, source_root: Path, seed_path: Path) -> tuple[dict[str, Any], str]:
    adapter = Path(__file__).with_name("p01_crw_dca_adapter_consumer_v1.py")
    command = [
        sys.executable,
        str(adapter),
        "--payload-dir",
        str(root),
        "--source-root",
        str(source_root),
        "--seed-request",
        str(seed_path),
        "--corpus",
        CORPUS_FILE,
        "--expected-corpus-sha256",
        EXPECTED_CORPUS_SHA256,
        "--expected-corpus-bytes",
        str(EXPECTED_CORPUS_BYTES),
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
    p.add_argument("--mm-source-root", required=True)
    p.add_argument("--mm-source-materialization", required=True)
    args = p.parse_args()

    source_root = Path(args.mm_source_root).resolve()
    source_materialization = _validate_mm_source(
        source_root, Path(args.mm_source_materialization).resolve()
    )

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
        contract = _validate_foundry_payload(root)
        seed = _build_w96_seed(source_root, root / CORPUS_FILE)
        seed_path = root / SEED_FILE
        seed_path.write_text(json.dumps(seed, sort_keys=True) + "\n", encoding="utf-8")
        adapter_receipt, inner_sha = _adapter_receipt(root, source_root, seed_path)

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
        "repository": "XoticHaze/mm-IBKR",
        "ref": source_materialization["source_ref"],
        "commit": source_materialization["source_sha"],
        "source_archive_sha256": source_materialization["source_archive_sha256"],
        "canonical_workload_blob_sha1": EXPECTED_WORKLOAD_BLOB_SHA1,
        "producer_identity": source_materialization.get("producer_identity"),
    }
    receipt["governed_corpus_lineage"] = {
        "repository": "XoticHaze/research-foundry",
        "research_foundry_ref": contract["research_foundry_ref"],
        "corpus_source_id": contract["corpus_source_id"],
        "dataset_sha256": EXPECTED_CORPUS_SHA256,
        "dataset_bytes": EXPECTED_CORPUS_BYTES,
    }
    receipt["seed_id"] = contract["seed_id"]
    receipt["primary_cost_contract"] = {
        "commission_points_per_contract_side": 0.3,
        "slippage_bps": 2.5,
        "spread_bps": 0.0,
    }
    receipt["adapter_receipt_sha256"] = inner_sha
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    print("P01_CRW_DCA_PUBLIC_RECEIPT=" + encoded)
    print("P01_CRW_DCA_PUBLIC_RECEIPT_SHA256=" + hashlib.sha256(encoded.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
