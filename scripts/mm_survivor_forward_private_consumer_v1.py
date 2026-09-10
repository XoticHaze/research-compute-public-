from __future__ import annotations

"""Fixed encrypted acceptance consumer for MM survivor-forward backend evidence.

The public plane receives only a one-run encrypted tarball containing an exact,
allow-listed private MM source/test set. Plaintext exists only in runner temp,
no arbitrary command is accepted from the payload, and output is sanitized to
PASS/FAIL plus exact input identity.
"""

import argparse
import base64
import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mm-survivor-forward-ephemeral-x25519-v1"
HARNESS = "mm_survivor_forward_backend_acceptance_v1"
AUTHORITY = "private_mm_source_validation_only"
INFO = b"mm-survivor-forward-ephemeral-v1"
EXPECTED_REPO = "XoticHaze/mm-IBKR"
EXPECTED_HEAD = "2e6042be2168b7db55fc45e76df99650bbe06919"
FILES = {
    "strategy_capital_readiness.py",
    "strategy_forward_intelligence.py",
    "strategy_health_canonical_trade_consumer.py",
    "strategy_health_evidence_pipeline.py",
    "strategy_health_historical_expectations.py",
    "strategy_health_position_context.py",
    "strategy_health_preview_attribution.py",
    "strategy_health_rolling_evidence.py",
    "tests/__init__.py",
    "tests/test_strategy_capital_readiness.py",
    "tests/test_strategy_capital_readiness_historical_compat.py",
    "tests/test_strategy_health_canonical_trade_forward_conformance.py",
    "tests/test_strategy_forward_intelligence.py",
}
TESTS = [
    "tests.test_strategy_capital_readiness",
    "tests.test_strategy_capital_readiness_historical_compat",
    "tests.test_strategy_health_canonical_trade_forward_conformance",
    "tests.test_strategy_forward_intelligence",
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({
        "schema": SCHEMA,
        "run_id": str(run_id),
        "authority": AUTHORITY,
        "harness": HARNESS,
        "recipient_key_id": recipient_key_id,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=hashlib.sha256(associated).digest(), info=INFO,
    ).derive(shared)


def extract_and_verify(payload: bytes, root: Path) -> dict:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        expected = FILES | {"payload-manifest.json"}
        if set(tf.getnames()) != expected:
            raise RuntimeError("private payload file set mismatch")
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root_resolved not in target.parents or not member.isfile():
                raise RuntimeError("unsafe private archive member")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "mm-survivor-forward-backend-payload-v1":
        raise RuntimeError("private payload schema mismatch")
    if manifest.get("harness") != HARNESS:
        raise RuntimeError("private payload harness mismatch")
    if manifest.get("private_repo") != EXPECTED_REPO or manifest.get("private_head") != EXPECTED_HEAD:
        raise RuntimeError("private payload repo/head mismatch")
    digests = manifest.get("files") or {}
    if set(digests) != FILES:
        raise RuntimeError("private payload manifest file set mismatch")
    for rel, digest in digests.items():
        if sha256(root / rel) != digest:
            raise RuntimeError(f"private payload inner digest mismatch: {rel}")
    return manifest


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env) != required:
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env["authority"] != AUTHORITY or env["harness"] != HARNESS:
        raise RuntimeError("envelope authority/harness mismatch")

    private_raw = b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != key_id:
        raise RuntimeError("recipient fingerprint mismatch")
    sender_raw = b64d(env["sender_public_b64"])
    nonce = b64d(env["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce length invalid")
    associated = aad(str(expected_run_id), key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(derive(shared, associated)).decrypt(nonce, b64d(env["ciphertext_b64"]), associated)
    if sha256_bytes(plaintext) != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = extract_and_verify(plaintext, root)
        compile_rc = subprocess.run(
            ["python", "-m", "py_compile",
             "strategy_capital_readiness.py", "strategy_forward_intelligence.py",
             "strategy_health_canonical_trade_consumer.py"],
            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
        test_rc = subprocess.run(
            ["python", "-m", "unittest", "-v", *TESTS],
            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode

    passed = compile_rc == 0 and test_rc == 0
    return {
        "schema": "mm-survivor-forward-backend-acceptance-receipt-v1",
        "authority": AUTHORITY,
        "harness": HARNESS,
        "private_repo": manifest["private_repo"],
        "private_head": manifest["private_head"],
        "status": "PASS" if passed else "FAIL",
        "checks": {"production_modules_compile": compile_rc == 0, "four_requested_test_modules_pass": test_rc == 0},
        "test_modules": TESTS,
        "payload_sha256": sha256_bytes(plaintext),
        "private_plaintext_emitted": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("MM_SURVIVOR_FORWARD_BACKEND_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
