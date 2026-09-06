from __future__ import annotations

"""Run-bound encrypted consumer for the fixed MM P03 operator-context contract."""

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "p03-private-binding-x25519-v1"
HARNESS = "mm_p03_preview_operator_binding_contract_v1"
INFO = b"commandcenter-p03-private-binding-v1"
ALLOWED_FILES = {
    "manifest.json",
    "strategy_health_preview_binding.py",
    "strategy_health_operator_context.py",
    "tests/test_strategy_health_preview_operator_context_binding.py",
    "tests/test_strategy_health_operator_context.py",
}
EXPECTED_TESTS = [
    "tests.test_strategy_health_preview_operator_context_binding",
    "tests.test_strategy_health_operator_context",
]
EXPECTED_MM_PR = 227


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


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
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)


def _validate_payload(plaintext: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
        names = {m.name for m in tf.getmembers() if m.isfile()}
        if names != ALLOWED_FILES:
            raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for member in tf.getmembers():
            p = Path(member.name)
            if member.isdir():
                continue
            if member.issym() or member.islnk() or p.is_absolute() or ".." in p.parts:
                raise RuntimeError("unsafe payload member")
        stream = tf.extractfile("manifest.json")
        if stream is None:
            raise RuntimeError("manifest missing")
        manifest = json.loads(stream.read().decode("utf-8"))
    required = {
        "schema", "harness", "authority", "mm_pr", "mm_head_sha", "test_modules",
        "binding_source_sha256", "binding_test_sha256", "operator_source_sha256", "operator_test_sha256",
    }
    if set(manifest) != required:
        raise RuntimeError("manifest field set mismatch")
    if manifest["schema"] != "p03-private-binding-payload-v2":
        raise RuntimeError("payload schema mismatch")
    if manifest["harness"] != HARNESS or manifest["authority"] != "research_only":
        raise RuntimeError("payload harness/authority mismatch")
    if int(manifest["mm_pr"]) != EXPECTED_MM_PR or manifest["test_modules"] != EXPECTED_TESTS:
        raise RuntimeError("payload target mismatch")
    return manifest


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
    aad = _aad(str(expected_run_id), expected_key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(nonce, ciphertext, aad)
    plaintext_sha = hashlib.sha256(plaintext).hexdigest()
    if plaintext_sha != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    manifest = _validate_payload(plaintext)
    with tempfile.TemporaryDirectory(prefix="p03-binding-") as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
            tf.extractall(root)
        checks = {
            "strategy_health_preview_binding.py": "binding_source_sha256",
            "tests/test_strategy_health_preview_operator_context_binding.py": "binding_test_sha256",
            "strategy_health_operator_context.py": "operator_source_sha256",
            "tests/test_strategy_health_operator_context.py": "operator_test_sha256",
        }
        for rel, field in checks.items():
            if hashlib.sha256((root / rel).read_bytes()).hexdigest() != manifest[field]:
                raise RuntimeError(f"private payload digest mismatch: {rel}")
        (root / "tests/__init__.py").write_text("", encoding="utf-8")
        proc = subprocess.run(
            ["python", "-m", "unittest", "-q", *EXPECTED_TESTS],
            cwd=root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            timeout=120,
        )
        return {
            "schema": "p03-private-binding-receipt-v2",
            "authority": "research_only",
            "harness": HARNESS,
            "mm_pr": EXPECTED_MM_PR,
            "mm_head_sha": manifest["mm_head_sha"],
            "payload_sha256": plaintext_sha,
            "test_modules": EXPECTED_TESTS,
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "exit_code": proc.returncode,
            "captured_output_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("P03_PRIVATE_BINDING_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    if receipt["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
