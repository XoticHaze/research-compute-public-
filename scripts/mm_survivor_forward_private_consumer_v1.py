from __future__ import annotations

"""One-run encrypted acceptance for the MM completed-trade operator summary contract.

Private MM source is decrypted only into public-runner temp, pinned to exact private
Git blobs, tested, reduced to a sanitized receipt, and then removed by the workflow.
"""

import argparse
import base64
import hashlib
import json
import runpy
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mm-survivor-forward-x25519-v1"
HARNESS = "mm_completed_trade_summary_contract_acceptance_v1"
INFO = b"commandcenter-mm-survivor-forward-v1"
EXPECTED_MM_COMMIT = "22e2aa068ac356eed6da9390f1c80afa58a8ac0e"
EXPECTED_GIT_BLOBS = {
    "scripts/operator/survivor_completed_trade_operator_summary_v1.py": "30c4ab9d45e9cfc4679177d5c2cb63c8d91d5bbb",
    "tests/test_survivor_completed_trade_operator_summary_v1.py": "f61d7a16e907ccc93745b1e84792f402391b6279",
}
FILES = set(EXPECTED_GIT_BLOBS)


def h(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "harness": HARNESS,
            "mm_commit": EXPECTED_MM_COMMIT,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=hashlib.sha256(associated).digest(), info=INFO,
    ).derive(shared)


def consume(envelope_path: Path, response_dir: Path, private_key_path: Path, run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    private = x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    recipient_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env.get("schema") != SCHEMA or str(env.get("run_id")) != str(run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env.get("harness") != HARNESS or env.get("mm_commit") != EXPECTED_MM_COMMIT:
        raise RuntimeError("envelope harness/MM commit mismatch")
    if env.get("recipient_key_id") != recipient_key_id:
        raise RuntimeError("recipient mismatch")

    encoded = []
    for item in env.get("chunks") or []:
        raw = (response_dir / Path(item["path"]).name).read_bytes()
        if h(raw) != item["sha256"] or len(raw.decode("ascii")) != int(item["chars"]):
            raise RuntimeError("chunk mismatch")
        encoded.append(raw.decode("ascii"))
    cipher = b64d("".join(encoded))
    if h(cipher) != env.get("ciphertext_sha256"):
        raise RuntimeError("cipher mismatch")

    associated = aad(run_id, recipient_key_id)
    sender = x25519.X25519PublicKey.from_public_bytes(b64d(env["sender_public_b64"]))
    plain = ChaCha20Poly1305(derive(private.exchange(sender), associated)).decrypt(
        b64d(env["nonce_b64"]), cipher, associated
    )
    if h(plain) != env.get("plaintext_sha256"):
        raise RuntimeError("plaintext mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive = root / "payload.tgz"
        archive.write_bytes(plain)
        with tarfile.open(archive, "r:gz") as tf:
            names = set(tf.getnames())
            if names != FILES | {"payload_manifest.json"}:
                raise RuntimeError("private payload file set mismatch")
            for member in tf.getmembers():
                if not member.isfile() or root.resolve() not in (root / member.name).resolve().parents:
                    raise RuntimeError("unsafe archive member")
            tf.extractall(root)
        archive.unlink()

        manifest = json.loads((root / "payload_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != "mm.survivor_forward_acceptance_payload.v1" or manifest.get("harness") != HARNESS or manifest.get("mm_commit") != EXPECTED_MM_COMMIT:
            raise RuntimeError("manifest identity mismatch")
        if set(manifest.get("files") or {}) != FILES:
            raise RuntimeError("manifest file set mismatch")
        identity = True
        for rel, expected_blob in EXPECTED_GIT_BLOBS.items():
            raw = (root / rel).read_bytes()
            identity = identity and manifest["files"].get(rel) == h(raw) and git_blob(raw) == expected_blob

        compile_rc = subprocess.run(
            [sys.executable, "-m", "py_compile", "scripts/operator/survivor_completed_trade_operator_summary_v1.py", "tests/test_survivor_completed_trade_operator_summary_v1.py"],
            cwd=root, capture_output=True, text=True,
        ).returncode

        tests_ok = True
        tests_run = 0
        sys.path.insert(0, str(root))
        try:
            namespace = runpy.run_path(str(root / "tests/test_survivor_completed_trade_operator_summary_v1.py"))
            for name, fn in sorted(namespace.items()):
                if name.startswith("test_") and callable(fn):
                    tests_run += 1
                    fn()
        except Exception:
            tests_ok = False
        finally:
            sys.path.pop(0)

        operator = runpy.run_path(str(root / "scripts/operator/survivor_completed_trade_operator_summary_v1.py"))
        canonical = {
            "schema": "mm.survivor_run_data_availability_audit.v1",
            "symbols": {
                "AMAT": {"bridge_ready_runs": 1, "evidence_incomplete_runs": 0, "intent_only_runs": 0, "ledger_only_runs": 0, "missing_evidence": []},
                "APH": {"bridge_ready_runs": 0, "evidence_incomplete_runs": 1, "intent_only_runs": 1, "ledger_only_runs": 0, "missing_evidence": ["paper_pnl_ledger.csv"]},
                "MNQ": {"bridge_ready_runs": 1, "evidence_incomplete_runs": 1, "intent_only_runs": 1, "ledger_only_runs": 0, "missing_evidence": ["paper_pnl_ledger.csv"]},
            },
        }
        projected = operator["project"](canonical)
        wire_ok = (
            projected.get("state") == "COHERENT"
            and [row.get("symbol") for row in projected.get("rows", [])] == ["AMAT", "APH", "MNQ"]
            and projected["rows"][1].get("state") == "INSUFFICIENT_EVIDENCE"
            and projected["rows"][2].get("state") == "BRIDGE_READY"
            and all(row.get("source_ref") == "mm.survivor_run_data_availability_audit.v1" for row in projected["rows"])
        )

    passed = identity and compile_rc == 0 and tests_ok and tests_run >= 6 and wire_ok
    return {
        "schema": "mm-completed-trade-summary-contract-acceptance-receipt-v1",
        "authority": "private_mm_source_validation_only",
        "harness": HARNESS,
        "mm_commit": EXPECTED_MM_COMMIT,
        "status": "PASS" if passed else "FAIL",
        "checks": {
            "reviewed_source_blob_identity_verified": bool(identity),
            "private_sources_compile": compile_rc == 0,
            "contract_regressions_pass": tests_ok and tests_run >= 6,
            "canonical_symbols_wire_shape_projects": bool(wire_ok),
            "bridge_ready_remains_input_availability_only": bool(wire_ok),
        },
        "tests_run": tests_run,
        "reviewed_source_blob_count": 2,
        "payload_sha256": h(plain),
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
    result = consume(Path(a.envelope), Path(a.response_dir), Path(a.private_key), a.run_id)
    print("MM_COMPLETED_TRADE_SUMMARY_RECEIPT=" + json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
