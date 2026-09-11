from __future__ import annotations

"""Focused encrypted acceptance for MM survivor benchmark-context projection."""

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

SCHEMA = "mm-survivor-benchmark-x25519-v1"
HARNESS = "mm_survivor_benchmark_private_acceptance_v1"
INFO = b"commandcenter-mm-survivor-benchmark-v1"
EXPECTED_MM_COMMIT = "7525295980af51dcdffe3dd222bf5e89923e9108"
EXPECTED_GIT_BLOBS = {
    "strategy_capital_readiness.py": "dddf48c557689413f469058bab2c0034958796e1",
    "strategy_forward_intelligence.py": "b0cd989166b4cefc94fbe80313de2728ba59ef78",
    "tests/test_strategy_forward_intelligence.py": "9cd355414783e1cf2e761d5ac2a177002ed94b51",
}
FILES = set(EXPECTED_GIT_BLOBS)


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({
        "schema": SCHEMA,
        "run_id": str(run_id),
        "harness": HARNESS,
        "mm_commit": EXPECTED_MM_COMMIT,
        "recipient_key_id": recipient_key_id,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=hashlib.sha256(associated).digest(), info=INFO).derive(shared)


def consume(envelope_path: Path, response_dir: Path, private_key_path: Path, run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    if env.get("schema") != SCHEMA or str(env.get("run_id")) != str(run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env.get("harness") != HARNESS or env.get("mm_commit") != EXPECTED_MM_COMMIT:
        raise RuntimeError("envelope harness/MM commit mismatch")

    private = x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env.get("recipient_key_id") != key_id:
        raise RuntimeError("recipient fingerprint mismatch")

    encoded = []
    for item in env.get("chunks") or []:
        raw = (response_dir / Path(item["path"]).name).read_bytes()
        if sha256_bytes(raw) != item.get("sha256") or len(raw.decode("ascii")) != int(item.get("chars", -1)):
            raise RuntimeError("encrypted chunk mismatch")
        encoded.append(raw.decode("ascii"))
    ciphertext = b64d("".join(encoded))
    if sha256_bytes(ciphertext) != env.get("ciphertext_sha256"):
        raise RuntimeError("ciphertext digest mismatch")

    sender = x25519.X25519PublicKey.from_public_bytes(b64d(env["sender_public_b64"]))
    nonce = b64d(env["nonce_b64"])
    associated = aad(run_id, key_id)
    plaintext = ChaCha20Poly1305(derive(private.exchange(sender), associated)).decrypt(nonce, ciphertext, associated)
    if sha256_bytes(plaintext) != env.get("plaintext_sha256"):
        raise RuntimeError("plaintext digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive = root / "payload.tar.gz"
        archive.write_bytes(plaintext)
        with tarfile.open(archive, "r:gz") as tf:
            expected = FILES | {"payload_manifest.json"}
            if set(tf.getnames()) != expected or any(not member.isfile() for member in tf.getmembers()):
                raise RuntimeError("payload file set mismatch")
            tf.extractall(root)
        manifest = json.loads((root / "payload_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != "mm.survivor_benchmark_acceptance_payload.v1" or manifest.get("mm_commit") != EXPECTED_MM_COMMIT or manifest.get("harness") != HARNESS:
            raise RuntimeError("payload manifest identity mismatch")
        for rel, expected_blob in EXPECTED_GIT_BLOBS.items():
            raw = (root / rel).read_bytes()
            if git_blob_sha1(raw) != expected_blob:
                raise RuntimeError(f"reviewed-source blob mismatch:{rel}")
            if sha256_bytes(raw) != (manifest.get("files") or {}).get(rel):
                raise RuntimeError(f"payload sha256 mismatch:{rel}")
        compile_rc = subprocess.run(["python", "-m", "py_compile", "strategy_capital_readiness.py", "strategy_forward_intelligence.py"], cwd=root).returncode
        test_rc = subprocess.run(["python", "-m", "unittest", "-v", "tests.test_strategy_forward_intelligence"], cwd=root).returncode

    passed = compile_rc == 0 and test_rc == 0
    return {
        "schema": "mm-survivor-benchmark-private-acceptance-receipt-v1",
        "status": "PASS" if passed else "FAIL",
        "mm_commit": EXPECTED_MM_COMMIT,
        "reviewed_source_blob_count": len(EXPECTED_GIT_BLOBS),
        "checks": {"reviewed_source_blob_identity_verified": True, "production_modules_compile": compile_rc == 0, "benchmark_test_module_pass": test_rc == 0},
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
    print("MM_SURVIVOR_BENCHMARK_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
