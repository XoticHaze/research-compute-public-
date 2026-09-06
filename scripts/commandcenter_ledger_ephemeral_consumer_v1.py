from __future__ import annotations

"""Fixed fail-closed consumer for the CommandCenter opportunity-ledger contract.

The public plane receives only a run-bound encrypted tarball. This consumer admits an
exact private file set, validates every inner digest, executes only the deterministic
ledger contract, and emits only a sanitized PASS/FAIL receipt. It has no runtime,
trading, promotion, or arbitrary-command authority.
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
from jsonschema import Draft202012Validator

SCHEMA = "commandcenter-opportunity-ledger-ephemeral-x25519-v1"
HARNESS = "commandcenter_opportunity_ledger_contract_v1"
AUTHORITY = "contract_validation_only"
INFO = b"commandcenter-opportunity-ledger-ephemeral-v1"
FILES = {
    "schemas/opportunity-ledger-event.v1.schema.json",
    "scripts/opportunity_ledger_replay.py",
    "tests/test_opportunity_ledger_replay.py",
    "tests/test_opportunity_ledger_replay_legacy_and_journal.py",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


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


def _extract(payload: bytes, root: Path) -> None:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        names = set(tf.getnames())
        expected = FILES | {"payload-manifest.json"}
        if names != expected:
            raise RuntimeError("ledger payload file set mismatch")
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root_resolved not in target.parents or not member.isfile():
                raise RuntimeError("unsafe ledger archive member")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "commandcenter-opportunity-ledger-contract-payload-v1":
        raise RuntimeError("ledger payload schema mismatch")
    if manifest.get("harness") != HARNESS:
        raise RuntimeError("ledger payload harness mismatch")
    digests = manifest.get("files") or {}
    if set(digests) != FILES:
        raise RuntimeError("ledger payload manifest file set mismatch")
    for rel, digest in digests.items():
        if sha256(root / rel) != digest:
            raise RuntimeError(f"ledger inner digest mismatch: {rel}")


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
        raise RuntimeError("ledger envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("ledger envelope run/schema mismatch")
    if env["authority"] != AUTHORITY or env["harness"] != HARNESS:
        raise RuntimeError("ledger envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("ledger recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != key_id:
        raise RuntimeError("ledger recipient fingerprint mismatch")

    sender_raw = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("ledger sender key/nonce length invalid")
    aad = _aad(str(expected_run_id), key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(
        nonce,
        _b64d(env["ciphertext_b64"]),
        aad,
    )
    if sha256_bytes(plaintext) != env["plaintext_sha256"]:
        raise RuntimeError("ledger decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _extract(plaintext, root)

        schema_ok = True
        try:
            schema = json.loads(
                (root / "schemas/opportunity-ledger-event.v1.schema.json").read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
        except Exception:
            schema_ok = False

        compile_rc = subprocess.run(
            ["python", "-m", "py_compile", "scripts/opportunity_ledger_replay.py"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        pytest_rc = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/test_opportunity_ledger_replay.py",
                "tests/test_opportunity_ledger_replay_legacy_and_journal.py",
            ],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    passed = schema_ok and compile_rc == 0 and pytest_rc == 0
    return {
        "schema": "commandcenter-opportunity-ledger-contract-receipt-v1",
        "authority": AUTHORITY,
        "harness": HARNESS,
        "status": "PASS" if passed else "FAIL",
        "checks": {
            "schema_valid": schema_ok,
            "replay_compiles": compile_rc == 0,
            "contract_tests_pass": pytest_rc == 0,
        },
        "payload_sha256": sha256_bytes(plaintext),
        "private_plaintext_emitted": False,
        "runtime_mutation": False,
        "live_trading_change": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("COMMANDCENTER_LEDGER_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
