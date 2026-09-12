from __future__ import annotations

"""One-run encrypted acceptance for MM completed-trade input-status composition."""

import argparse
import base64
import hashlib
import io
import json
import runpy
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mm-survivor-forward-x25519-v1"
HARNESS = "mm_completed_trade_input_status_acceptance_v1"
INFO = b"commandcenter-mm-survivor-forward-v1"
EXPECTED_MM_COMMIT = "9eb42ce1416b2b7ced51fd8ee77c9ae886c27fe3"
EXPECTED_GIT_BLOBS = {
    "scripts/operator/survivor_completed_trade_input_status_v1.py": "d439186bdbac159ee1e7a178e184de522b6acb64",
    "tests/test_survivor_completed_trade_input_status_v1.py": "4e70f96ef51b2e75c9afadd2f4c3c2838c9545e1",
}
FILES = set(EXPECTED_GIT_BLOBS)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def aad(run_id: str, key_id: str) -> bytes:
    return json.dumps({
        "schema": SCHEMA, "run_id": str(run_id), "harness": HARNESS,
        "mm_commit": EXPECTED_MM_COMMIT, "recipient_key_id": key_id,
    }, sort_keys=True, separators=(",", ":")).encode()


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=hashlib.sha256(associated).digest(), info=INFO).derive(shared)


def _audit_stub(root: Path) -> dict:
    targets = ("AMAT", "APH", "MNQ")
    candidates = sorted({p.parent for name in ("order_intents.jsonl", "paper_pnl_ledger.csv") for p in root.rglob(name)})
    symbols = {s: {"bridge_ready_runs": 0, "evidence_incomplete_runs": 0,
                   "intent_only_runs": 0, "ledger_only_runs": 0, "missing_evidence": []} for s in targets}
    ready_runs = 0
    for run in candidates:
        intents = run / "order_intents.jsonl"
        ledger = run / "paper_pnl_ledger.csv"
        intent_text = intents.read_text(encoding="utf-8") if intents.is_file() else ""
        ledger_text = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
        for symbol in targets:
            present_intent = symbol in intent_text
            present_ledger = symbol in ledger_text
            if present_intent and present_ledger:
                symbols[symbol]["bridge_ready_runs"] += 1
                ready_runs += 1
            elif present_intent:
                symbols[symbol]["intent_only_runs"] += 1
                symbols[symbol]["missing_evidence"] = ["paper_pnl_ledger.csv"]
            elif present_ledger:
                symbols[symbol]["ledger_only_runs"] += 1
                symbols[symbol]["missing_evidence"] = ["order_intents.jsonl"]
    return {
        "schema": "mm.survivor_run_data_availability_audit.v1",
        "root": str(root), "candidate_run_count": len(candidates),
        "bridge_ready_run_count": ready_runs, "symbols": symbols,
        "authority": "read_only_existing_paper_executor_evidence",
        "no_identity_inference": True,
    }


def _project_stub(audit: dict) -> dict:
    rows = []
    for symbol in ("AMAT", "APH", "MNQ"):
        item = audit["symbols"][symbol]
        ready = int(item.get("bridge_ready_runs") or 0)
        incomplete = int(item.get("evidence_incomplete_runs") or 0)
        intents = int(item.get("intent_only_runs") or 0)
        ledgers = int(item.get("ledger_only_runs") or 0)
        missing = list(item.get("missing_evidence") or [])
        state = "BRIDGE_READY" if ready else ("INSUFFICIENT_EVIDENCE" if incomplete or intents or ledgers or missing else "UNKNOWN")
        rows.append({"symbol": symbol, "state": state, "bridge_ready_runs": ready,
                     "evidence_incomplete_runs": incomplete, "intent_only_runs": intents,
                     "ledger_only_runs": ledgers, "missing": missing,
                     "source_ref": audit["schema"], "coherent": True, "problems": []})
    return {"schema": "mm.survivor_completed_trade_operator_summary.v1",
            "source_schema": audit["schema"], "state": "COHERENT", "rows": rows,
            "boundary": "INPUT_AVAILABILITY_ONLY"}


def _install_dependency_stubs() -> None:
    audit_mod = types.ModuleType("scripts.operator.audit_survivor_run_data_availability_v1")
    audit_mod.audit_root = _audit_stub
    summary_mod = types.ModuleType("scripts.operator.survivor_completed_trade_operator_summary_v1")
    summary_mod.project = _project_stub
    summary_mod.render = lambda summary: json.dumps(summary, sort_keys=True)
    sys.modules[audit_mod.__name__] = audit_mod
    sys.modules[summary_mod.__name__] = summary_mod


def consume(envelope_path: Path, response_dir: Path, private_key_path: Path, run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    private = x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env.get("schema") != SCHEMA or str(env.get("run_id")) != str(run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env.get("harness") != HARNESS or env.get("mm_commit") != EXPECTED_MM_COMMIT or env.get("recipient_key_id") != key_id:
        raise RuntimeError("envelope authority identity mismatch")

    encoded = []
    for item in env.get("chunks") or []:
        raw = (response_dir / Path(item["path"]).name).read_bytes()
        if sha256_bytes(raw) != item["sha256"] or len(raw.decode("ascii")) != int(item["chars"]):
            raise RuntimeError("chunk mismatch")
        encoded.append(raw.decode("ascii"))
    ciphertext = b64d("".join(encoded))
    if sha256_bytes(ciphertext) != env.get("ciphertext_sha256"):
        raise RuntimeError("ciphertext mismatch")
    associated = aad(run_id, key_id)
    sender = x25519.X25519PublicKey.from_public_bytes(b64d(env["sender_public_b64"]))
    plain = ChaCha20Poly1305(derive(private.exchange(sender), associated)).decrypt(b64d(env["nonce_b64"]), ciphertext, associated)
    if sha256_bytes(plain) != env.get("plaintext_sha256"):
        raise RuntimeError("plaintext mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive = root / "payload.tgz"
        archive.write_bytes(plain)
        with tarfile.open(archive, "r:gz") as tf:
            if set(tf.getnames()) != FILES | {"payload_manifest.json"}:
                raise RuntimeError("private payload file set mismatch")
            for member in tf.getmembers():
                if not member.isfile() or root.resolve() not in (root / member.name).resolve().parents:
                    raise RuntimeError("unsafe archive member")
            tf.extractall(root)
        archive.unlink()
        manifest = json.loads((root / "payload_manifest.json").read_text())
        if manifest.get("schema") != "mm.survivor_forward_acceptance_payload.v1" or manifest.get("harness") != HARNESS or manifest.get("mm_commit") != EXPECTED_MM_COMMIT:
            raise RuntimeError("manifest identity mismatch")
        if set(manifest.get("files") or {}) != FILES:
            raise RuntimeError("manifest file set mismatch")
        identity = True
        for rel, blob in EXPECTED_GIT_BLOBS.items():
            path = root / rel
            identity = identity and manifest["files"][rel] == sha256_bytes(path.read_bytes()) and git_blob(path) == blob

        compile_rc = subprocess.run([sys.executable, "-m", "py_compile", *sorted(FILES)], cwd=root, capture_output=True).returncode
        sys.path.insert(0, str(root))
        _install_dependency_stubs()
        try:
            namespace = runpy.run_path(str(root / "tests/test_survivor_completed_trade_input_status_v1.py"))
            case = namespace["SurvivorCompletedTradeInputStatusTests"]
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
            stream = io.StringIO()
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            tests_run = result.testsRun
            tests_ok = result.wasSuccessful()
        finally:
            sys.path.pop(0)

    passed = bool(identity and compile_rc == 0 and tests_ok and tests_run == 4)
    return {
        "schema": "mm-completed-trade-input-status-acceptance-receipt-v1",
        "authority": "private_mm_source_validation_only",
        "harness": HARNESS,
        "mm_commit": EXPECTED_MM_COMMIT,
        "status": "PASS" if passed else "FAIL",
        "checks": {
            "reviewed_source_blob_identity_verified": bool(identity),
            "private_sources_compile": compile_rc == 0,
            "composition_regressions_pass": tests_ok and tests_run == 4,
            "missing_and_empty_roots_fail_closed": tests_ok,
            "partial_and_bridge_ready_states_operator_visible": tests_ok,
            "input_availability_only_boundary_preserved": tests_ok,
        },
        "tests_run": tests_run,
        "reviewed_source_blob_count": 2,
        "payload_sha256": sha256_bytes(plain),
        "private_plaintext_emitted": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--response-dir", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    a = p.parse_args()
    receipt = consume(Path(a.envelope), Path(a.response_dir), Path(a.private_key), a.run_id)
    print("MM_COMPLETED_TRADE_INPUT_STATUS_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
