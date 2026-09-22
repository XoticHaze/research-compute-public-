from __future__ import annotations

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

SCHEMA = "commandcenter-linux-host-validation-x25519-v1"
HARNESS = "commandcenter_linux_host_ingestion_r1"
AUTHORITY = "commandcenter_host_contract_only"
INFO = b"commandcenter-linux-host-validation-r1"
PRIVATE_REPO = "XoticHaze/CommandCenter"
PRIVATE_BRANCH = "assistant/linux-host-ingestion-r1"
PRIVATE_HEAD = "968accac5bb72f515471ee2adc6c703f1d3341e8"
CATALOG_SHA256 = "a39ca7d2f269e3ea5f89c2ccf905b900d4c8c2e88abb8700db2fbd4d53a883cc"
EXPECTED_BLOBS = {
    "commandcenter/__init__.py": "b9300dcea4eecb4c100fe2e097ef32569ac3482e",
    "commandcenter/host_device_contract.py": "c05586216dec00be6a6f5fe19fe2e8507009abcf",
    "commandcenter/host_device_linux.py": "667bfa464964b4e40846fdb028ef4c9f949f6cfc",
    "commandcenter/host_device_spool_consumer.py": "a59e99a8047345095879db92f8718f1af772518e",
    "config/hosts/steamdeck-linux-r1.json": "ba487420ba55c3f3342fc6d09f75aea0011d649f",
    "scripts/bootstrap-linux-host.sh": "259195b85f11dc3f591b842e2a753be3894dc8d6",
    "tests/test_host_device_linux_r1.py": "1ec8125e249cd73ade27feca53d5fac39dc743bd",
}
ALLOWED_FILES = {"manifest.json", *EXPECTED_BLOBS}


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _git_blob_sha(raw: bytes) -> str:
    prefix = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + raw).hexdigest()


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
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


def _decrypt(envelope_path: Path, private_key_path: Path, run_id: str) -> bytes:
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
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env["authority"] != AUTHORITY or env["harness"] != HARNESS:
        raise RuntimeError("envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    recipient_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != recipient_key_id:
        raise RuntimeError("recipient key fingerprint mismatch")

    sender_raw = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    ciphertext = _b64d(env["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce length invalid")
    aad = _aad(str(run_id), recipient_key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")
    return plaintext


def _read_payload(plaintext: bytes) -> tuple[dict, dict[str, bytes]]:
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
        members = [member for member in tf.getmembers() if member.isfile()]
        names = {member.name for member in members}
        if names != ALLOWED_FILES:
            raise RuntimeError("payload file set mismatch")
        blobs: dict[str, bytes] = {}
        for member in tf.getmembers():
            path = Path(member.name)
            if member.isdir():
                continue
            if member.issym() or member.islnk() or path.is_absolute() or ".." in path.parts:
                raise RuntimeError("unsafe payload member")
            stream = tf.extractfile(member)
            if stream is None:
                raise RuntimeError("payload member unreadable")
            blobs[member.name] = stream.read()

    manifest = json.loads(blobs.pop("manifest.json").decode("utf-8"))
    required = {
        "schema",
        "harness",
        "authority",
        "private_repo",
        "private_branch",
        "private_head",
        "catalog_sha256",
        "git_blob_sha",
    }
    if set(manifest) != required:
        raise RuntimeError("manifest field set mismatch")
    if manifest["schema"] != "commandcenter-linux-host-validation-payload-v1":
        raise RuntimeError("payload schema mismatch")
    if manifest["harness"] != HARNESS or manifest["authority"] != AUTHORITY:
        raise RuntimeError("payload harness/authority mismatch")
    if manifest["private_repo"] != PRIVATE_REPO:
        raise RuntimeError("private repository identity mismatch")
    if manifest["private_branch"] != PRIVATE_BRANCH or manifest["private_head"] != PRIVATE_HEAD:
        raise RuntimeError("private branch/head identity mismatch")
    if manifest["catalog_sha256"] != CATALOG_SHA256:
        raise RuntimeError("catalog identity mismatch")
    if manifest["git_blob_sha"] != EXPECTED_BLOBS:
        raise RuntimeError("manifest Git blob map mismatch")

    for relpath, expected in EXPECTED_BLOBS.items():
        if _git_blob_sha(blobs[relpath]) != expected:
            raise RuntimeError(f"private Git blob identity mismatch: {relpath}")
    return manifest, blobs


def _write_payload(root: Path, blobs: dict[str, bytes]) -> None:
    for relpath, raw in blobs.items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 120):
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, hashlib.sha256(proc.stdout).hexdigest()


def consume(envelope_path: Path, private_key_path: Path, run_id: str) -> dict:
    plaintext = _decrypt(envelope_path, private_key_path, run_id)
    _, blobs = _read_payload(plaintext)

    with tempfile.TemporaryDirectory(prefix="cc-linux-host-r1-") as td:
        root = Path(td)
        _write_payload(root, blobs)
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(root),
            "HOME": str(root / "home"),
        }
        (root / "home").mkdir()

        compile_rc, compile_sha = _run(
            [
                "python",
                "-m",
                "py_compile",
                "commandcenter/host_device_contract.py",
                "commandcenter/host_device_linux.py",
                "commandcenter/host_device_spool_consumer.py",
                "tests/test_host_device_linux_r1.py",
            ],
            cwd=root,
            env=env,
        )
        if compile_rc != 0:
            raise RuntimeError("private Linux host source compile failed")

        test_rc, test_sha = _run(
            ["python", "-m", "unittest", "-v", "tests.test_host_device_linux_r1"],
            cwd=root,
            env=env,
        )
        if test_rc != 0:
            raise RuntimeError("private Linux host focused tests failed")

        dry_rc, dry_sha = _run(
            ["bash", "scripts/bootstrap-linux-host.sh"],
            cwd=root,
            env=env,
        )
        if dry_rc != 0:
            raise RuntimeError("private Linux host bootstrap dry-run failed")

    return {
        "schema": "commandcenter-linux-host-validation-receipt-v1",
        "authority": AUTHORITY,
        "harness": HARNESS,
        "private_repo": PRIVATE_REPO,
        "private_branch": PRIVATE_BRANCH,
        "private_head": PRIVATE_HEAD,
        "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
        "catalog_sha256": CATALOG_SHA256,
        "git_blob_identity_verified": True,
        "compile_status": "PASS",
        "compile_output_sha256": compile_sha,
        "test_status": "PASS",
        "test_output_sha256": test_sha,
        "bootstrap_dry_run_status": "PASS",
        "bootstrap_output_sha256": dry_sha,
        "plaintext_published": False,
        "host_mutation": False,
        "network_authority_bound": False,
        "physical_device_touched": False,
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("COMMANDCENTER_LINUX_HOST_VALIDATION_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
