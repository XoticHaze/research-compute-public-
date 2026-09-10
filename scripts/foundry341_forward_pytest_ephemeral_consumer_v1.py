from __future__ import annotations

"""Run-bound encrypted acceptance for the Foundry #341 forward-observer consumer.

The public repository never stores plaintext private Foundry source. A one-run X25519
recipient receives a ChaCha20Poly1305-sealed tarball, validates an exact payload/file
identity, executes only the fixed pytest modules, and emits a sanitized PASS/FAIL receipt.
"""

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

SCHEMA = "foundry341-forward-pytest-x25519-v1"
HARNESS = "foundry341_forward_observer_pytest_v1"
INFO = b"commandcenter-foundry341-forward-pytest-v1"
FOUNDRY_PR = 341
FOUNDRY_HEAD = "53931308f798c107ab0aed16da0a1268ec589266"
TEST_FILES = [
    "tests/test_forward_observation_contract_spmo_smallvalue.py",
    "tests/test_forward_observation_next_executable_spmo_smallvalue.py",
    "tests/test_seal_spmo_smallvalue_forward_decision.py",
    "tests/test_mature_spmo_smallvalue_forward_outcome.py",
]
PAYLOAD_FILES = {
    "research/forward_observation_contract_spmo_smallvalue_20260910.json",
    "research/forward_observation_next_executable_spmo_smallvalue_20260910.json",
    "research/validate_forward_observation_contract.py",
    "research/seal_spmo_smallvalue_forward_decision.py",
    "research/mature_spmo_smallvalue_forward_outcome.py",
    "shared_evidence/claims/p303_p304_spmo_smallvalue_fixed_utility_supported.v1.json",
    "shared_evidence/claims/p305_spmo_smallvalue_cost_robustness_supported.v1.json",
    *TEST_FILES,
}
ALLOWED_FILES = {"manifest.json", *PAYLOAD_FILES}


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


def _validated_payload(plaintext: bytes) -> tuple[dict, str]:
    payload_sha = hashlib.sha256(plaintext).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        names = {m.name for m in members}
        if names != ALLOWED_FILES:
            raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for member in tf.getmembers():
            p = Path(member.name)
            if member.isdir():
                continue
            if member.issym() or member.islnk() or p.is_absolute() or ".." in p.parts:
                raise RuntimeError("unsafe payload member")
        mf = tf.extractfile(tf.getmember("manifest.json"))
        if mf is None:
            raise RuntimeError("manifest missing")
        manifest = json.loads(mf.read().decode("utf-8"))
    required = {
        "schema",
        "harness",
        "authority",
        "foundry_pr",
        "foundry_head_sha",
        "test_files",
        "file_sha256",
    }
    if set(manifest) != required:
        raise RuntimeError("manifest field set mismatch")
    if manifest["schema"] != "foundry341-forward-pytest-payload-v1":
        raise RuntimeError("payload schema mismatch")
    if manifest["harness"] != HARNESS or manifest["authority"] != "research_only":
        raise RuntimeError("payload harness/authority mismatch")
    if int(manifest["foundry_pr"]) != FOUNDRY_PR or manifest["foundry_head_sha"] != FOUNDRY_HEAD:
        raise RuntimeError("payload target mismatch")
    if manifest["test_files"] != TEST_FILES:
        raise RuntimeError("test target mismatch")
    if set(manifest["file_sha256"]) != PAYLOAD_FILES:
        raise RuntimeError("file digest manifest mismatch")
    return manifest, payload_sha


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "run_id",
        "authority",
        "harness",
        "recipient_key_id",
        "sender_public_b64",
        "nonce_b64",
        "ciphertext_b64",
        "plaintext_sha256",
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

    manifest, payload_sha = _validated_payload(plaintext)
    with tempfile.TemporaryDirectory(prefix="foundry341-forward-") as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
            tf.extractall(root)
        for rel, expected in manifest["file_sha256"].items():
            actual = hashlib.sha256((root / rel).read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(f"private file digest mismatch: {rel}")
        (root / "research/__init__.py").write_text("", encoding="utf-8")
        (root / "tests/__init__.py").write_text("", encoding="utf-8")
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q", *TEST_FILES],
            cwd=root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            timeout=180,
        )
        output_sha = hashlib.sha256(proc.stdout).hexdigest()
        status = "PASS" if proc.returncode == 0 else "FAIL"
        return {
            "schema": "foundry341-forward-pytest-receipt-v1",
            "authority": "research_only",
            "harness": HARNESS,
            "foundry_pr": FOUNDRY_PR,
            "foundry_head_sha": FOUNDRY_HEAD,
            "payload_sha256": payload_sha,
            "test_files": TEST_FILES,
            "status": status,
            "exit_code": proc.returncode,
            "captured_output_sha256": output_sha,
            "protected_authority_crossed": False,
        }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("FOUNDRY341_FORWARD_PYTEST_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    if receipt["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
