from __future__ import annotations

"""Fixed encrypted validator for private Foundry Model Forward registry changes.

The public runner receives only a one-run authenticated ciphertext. The decrypted payload
is restricted to the exact Model Forward registry/admission test file set and is executed
in temporary storage. Public logs expose only a sanitized pass/fail receipt, never source,
test stdout/stderr, model observations, or private paths outside the declared relative set.
"""

import argparse
import base64
import hashlib
import io
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

SCHEMA = "model-forward-registry-validation-x25519-v1"
PAYLOAD_SCHEMA = "research-foundry-model-forward-registry-validation-v1"
HARNESS = "model_forward_registry_validation_v1"
INFO = b"research-foundry-model-forward-registry-validation-v1"
ALLOWED_FILES = {
    "model_forward/registry.v1.json",
    "model_forward/registry.py",
    "model_forward/admit_observation.py",
    "model_forward/build_model_index.py",
    "model_forward/manifests/p46.v1.json",
    "tests/test_model_forward_registry.py",
}


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _key_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": "validation_only",
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


def _decrypt(envelope: dict, private_raw: bytes, run_id: str) -> bytes:
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
    if set(envelope) != required:
        raise RuntimeError("envelope field-set mismatch")
    if envelope["schema"] != SCHEMA or str(envelope["run_id"]) != str(run_id):
        raise RuntimeError("run identity mismatch")
    if envelope["authority"] != "validation_only" or envelope["harness"] != HARNESS:
        raise RuntimeError("authority/harness mismatch")

    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    expected_id = _key_id(recipient_raw)
    if envelope["recipient_key_id"] != expected_id:
        raise RuntimeError("recipient fingerprint mismatch")

    sender_raw = _b64d(envelope["sender_public_b64"])
    nonce = _b64d(envelope["nonce_b64"])
    ciphertext = _b64d(envelope["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce shape invalid")
    aad = _aad(run_id, expected_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != envelope["plaintext_sha256"]:
        raise RuntimeError("plaintext digest mismatch")
    return plaintext


def _extract(payload: bytes, root: Path) -> dict:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        names = {member.name for member in members if member.isfile()}
        expected = {"payload-manifest.json", *ALLOWED_FILES}
        if names != expected:
            raise RuntimeError(f"payload file-set mismatch: {sorted(names ^ expected)}")
        for member in members:
            if not member.isfile():
                continue
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("unsafe payload path")
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"unable to read payload member {member.name}")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())

    manifest_path = root / "payload-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != PAYLOAD_SCHEMA or manifest.get("harness") != HARNESS:
        raise RuntimeError("payload manifest identity mismatch")
    expected_hashes = manifest.get("files") or {}
    if set(expected_hashes) != ALLOWED_FILES:
        raise RuntimeError("payload manifest file-set mismatch")
    for relative, expected_hash in expected_hashes.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected_hash:
            raise RuntimeError(f"payload digest mismatch: {relative}")
    return manifest


def _validate(root: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_model_forward_registry.py",
            "-v",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )
    return {
        "returncode": int(run.returncode),
        "passed": run.returncode == 0,
        "stdout_sha256": hashlib.sha256(run.stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(run.stderr.encode("utf-8")).hexdigest(),
    }


def consume(envelope_path: Path, private_key_path: Path, run_id: str) -> dict:
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("private key length invalid")
    plaintext = _decrypt(envelope, private_raw, run_id)
    with tempfile.TemporaryDirectory(prefix="model-forward-registry-") as temp:
        root = Path(temp)
        manifest = _extract(plaintext, root)
        result = _validate(root)
    return {
        "schema": "model-forward-registry-validation-receipt-v1",
        "authority": "validation_only",
        "harness": HARNESS,
        "run_id": str(run_id),
        "source_file_count": len(ALLOWED_FILES),
        "payload_sha256": envelope["plaintext_sha256"],
        "declared_source_head": manifest.get("source_head"),
        "tests_passed": result["passed"],
        "test_returncode": result["returncode"],
        "test_stdout_sha256": result["stdout_sha256"],
        "test_stderr_sha256": result["stderr_sha256"],
        "private_source_persisted": False,
        "private_test_output_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("MODEL_FORWARD_REGISTRY_VALIDATION_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    if not receipt["tests_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
