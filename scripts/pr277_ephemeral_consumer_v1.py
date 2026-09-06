from __future__ import annotations

"""One-run X25519 consumer for the fixed private PR277 research harness.

The public runner owns an ephemeral private key only for one job. The private
authority sends an encrypted tarball containing the exact frozen PR277 evaluator
closure. Plaintext is extracted only in runner temp, subprocess output is captured,
and only a bounded aggregate receipt is printed.
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "pr277-ephemeral-x25519-v1"
HARNESS = "research_foundry_pr277_domain_shift_v1"
INFO = b"commandcenter-pr277-ephemeral-v1"
PAYLOAD_SCHEMA = "research-foundry-pr277-domain-shift-payload-v1"
RESULT = "research/results/semiconductor_scarcity_domain_shift_20260905.json"
PRIVATE_FILES = {
    "research/run_semiconductor_scarcity_domain_shift_20260905.py",
    "research/run_survivor_entry_external_transport_20260902.py",
    "research/run_survivor_entry_predicted_value_ranker_20260905.py",
    "research/run_survivor_entry_value_20260902.py",
    "research/run_survivor_fixed10_vs20_capital_20260902.py",
    "research/survivor_ranker_fresh_confirmation_contract_20260905.json",
}


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": "research_only",
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes) -> bytes:
    salt = hashlib.sha256(aad).digest()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=INFO).derive(shared)


def _safe_extract(payload: bytes, root: Path) -> dict:
    archive_path = root / "payload.tar.gz"
    archive_path.write_bytes(payload)
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            names = set(tf.getnames())
            expected = PRIVATE_FILES | {"payload-manifest.json"}
            if names != expected:
                raise RuntimeError(f"PR277 payload file set mismatch: {sorted(names)}")
            for member in tf.getmembers():
                if not member.isfile():
                    raise RuntimeError("non-file archive member rejected")
                target = (root / member.name).resolve()
                if root.resolve() not in target.parents:
                    raise RuntimeError("archive path traversal rejected")
            tf.extractall(root)
    finally:
        archive_path.unlink(missing_ok=True)

    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if set(manifest) != {"schema", "harness", "source", "files"}:
        raise RuntimeError("PR277 payload manifest field set mismatch")
    if manifest["schema"] != PAYLOAD_SCHEMA or manifest["harness"] != HARNESS:
        raise RuntimeError("PR277 payload manifest identity mismatch")
    files = manifest["files"]
    if set(files) != PRIVATE_FILES:
        raise RuntimeError("PR277 payload manifest file set mismatch")
    for rel, digest in files.items():
        if _sha256(root / rel) != digest:
            raise RuntimeError(f"PR277 inner digest mismatch: {rel}")
    return manifest


def _run_private(root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    completed = subprocess.run(
        [sys.executable, "-m", "research.run_semiconductor_scarcity_domain_shift_20260905"],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=1500,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"private PR277 harness failed rc={completed.returncode}")
    result_path = root / RESULT
    if not result_path.is_file():
        raise RuntimeError("private PR277 result missing")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("schema") != "foundry.research.semiconductor_scarcity_domain_shift.v1":
        raise RuntimeError("private PR277 result schema mismatch")
    if result.get("research_only") is not True or result.get("promotion_authority") is not False:
        raise RuntimeError("private PR277 authority boundary mismatch")
    return {
        "result_sha256": _sha256(result_path),
        "unified_common_cutoff": result.get("unified_common_cutoff"),
        "unified_common_calendar_rows": result.get("unified_common_calendar_rows"),
        "dominant_drift_groups": result.get("dominant_drift_groups"),
        "group_drift_rollup": result.get("group_drift_rollup"),
        "admission_support": result.get("admission_support"),
        "cohort_state_summary": result.get("cohort_state_summary"),
        "descriptive_scarcity_reproduction_200bps": result.get("descriptive_scarcity_reproduction_200bps"),
    }


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {
        "schema", "run_id", "authority", "harness", "recipient_key_id",
        "sender_public_b64", "nonce_b64", "ciphertext_b64", "plaintext_sha256",
    }
    if set(env) != required:
        raise RuntimeError("ephemeral envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("ephemeral envelope run identity mismatch")
    if env["authority"] != "research_only" or env["harness"] != HARNESS:
        raise RuntimeError("ephemeral envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    expected_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != expected_key_id:
        raise RuntimeError("recipient key fingerprint mismatch")

    sender_raw = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    ciphertext = _b64d(env["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("ephemeral envelope key/nonce length invalid")
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    aad = _aad(str(expected_run_id), expected_key_id)
    key = _derive(shared, aad)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if _sha256_bytes(plaintext) != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory(prefix="pr277-private-") as td:
        root = Path(td)
        manifest = _safe_extract(plaintext, root)
        private_result = _run_private(root)
    return {
        "schema": "pr277-sealed-consumer-receipt-v1",
        "authority": "research_only",
        "harness": HARNESS,
        "source": manifest["source"],
        "private_result": private_result,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("PR277_EPHEMERAL_RECEIPT=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
