from __future__ import annotations

"""Fixed fail-closed consumer for research-foundry P06 two-pool slow funding.

The public plane receives only a run-bound encrypted tarball. This consumer admits an
exact private file set, validates every inner digest, executes one fixed module, and
emits only sanitized decision/metric fields. It provides no command or runtime input.
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

SCHEMA = "p06-slow-funding-ephemeral-x25519-v1"
HARNESS = "research_foundry_p06_slow_funding_216_v1"
INFO = b"commandcenter-p06-slow-funding-ephemeral-v1"
FILES = {
    "research/run_slow_sector_funding_216_20260904.py",
    "research/run_industry_generic_entry_transport_20260902.py",
    "research/run_entry_cross_sector_reverse_transfer_20260902.py",
    "research/run_survivor_entry_value_20260902.py",
    "research/run_survivor_fixed10_vs20_capital_20260902.py",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({"schema": SCHEMA, "run_id": str(run_id), "authority": "research_only", "harness": HARNESS, "recipient_key_id": recipient_key_id}, sort_keys=True, separators=(",", ":")).encode()


def _derive(shared: bytes, aad: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=INFO).derive(shared)


def _extract(payload: bytes, root: Path) -> None:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        names = set(tf.getnames())
        expected = FILES | {"payload-manifest.json"}
        if names != expected:
            raise RuntimeError(f"P06 payload file set mismatch: {sorted(names)}")
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root.resolve() not in target.parents or not member.isfile():
                raise RuntimeError("unsafe P06 archive member")
        tf.extractall(root)
    archive.unlink(missing_ok=True)
    manifest = json.loads((root / "payload-manifest.json").read_text())
    if manifest.get("schema") != "research-foundry-p06-slow-funding-payload-v1" or manifest.get("harness") != HARNESS:
        raise RuntimeError("P06 payload identity mismatch")
    digests = manifest.get("files") or {}
    if set(digests) != FILES:
        raise RuntimeError("P06 payload manifest file set mismatch")
    for rel, digest in digests.items():
        if sha256(root / rel) != digest:
            raise RuntimeError(f"P06 inner digest mismatch: {rel}")


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text())
    required = {"schema", "run_id", "authority", "harness", "recipient_key_id", "sender_public_b64", "nonce_b64", "ciphertext_b64", "plaintext_sha256"}
    if set(env) != required or env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id) or env["authority"] != "research_only" or env["harness"] != HARNESS:
        raise RuntimeError("P06 envelope identity mismatch")
    private = x25519.X25519PrivateKey.from_private_bytes(_b64d(private_key_path.read_text().strip()))
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != key_id:
        raise RuntimeError("P06 recipient key mismatch")
    aad = _aad(expected_run_id, key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(_b64d(env["sender_public_b64"])))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(_b64d(env["nonce_b64"]), _b64d(env["ciphertext_b64"]), aad)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("P06 decrypted payload digest mismatch")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _extract(plaintext, root)
        completed = subprocess.run(["python", "-m", "research.run_slow_sector_funding_216_20260904"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"P06 fixed harness failed rc={completed.returncode}")
        result_path = root / "research/results/slow_sector_funding_216_20260904.json"
        result = json.loads(result_path.read_text())
        safe = {k: result.get(k) for k in ("classification", "decision", "window", "cost_bps", "router_folds", "summary", "controls", "concentration") if k in result}
        return {"schema": "p06-slow-funding-sanitized-receipt-v1", "authority": "research_only", "harness": HARNESS, "result_sha256": sha256(result_path), "result": safe}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    print("P06_SLOW_FUNDING_RECEIPT=" + json.dumps(consume(Path(args.envelope), Path(args.private_key), args.run_id), sort_keys=True))


if __name__ == "__main__":
    main()
