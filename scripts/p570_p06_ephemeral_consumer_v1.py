from __future__ import annotations

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

SCHEMA = "p06-slow-funding-ephemeral-x25519-v1"
HARNESS = "research_foundry_p06_slow_funding_216_v1"
INFO = b"commandcenter-p06-slow-funding-ephemeral-v1"
PAYLOAD_SCHEMA = "research-foundry-p06-slow-funding-payload-v1"
ALLOWED_FILES = {
    "research/run_slow_sector_funding_216_20260904.py",
    "research/run_industry_generic_entry_transport_20260902.py",
    "research/run_entry_cross_sector_reverse_transfer_20260902.py",
    "research/run_survivor_entry_value_20260902.py",
    "research/run_survivor_fixed10_vs20_capital_20260902.py",
    "research/run_p570_p06_rare_marginal_tilt_20260911.py",
}
RESULT = "research/results/p570_p06_rare_marginal_tilt_20260911.json"


def b64d(v: str) -> bytes:
    return base64.b64decode(v.encode("ascii"), validate=True)


def key_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({"schema": SCHEMA, "run_id": str(run_id), "authority": "research_only", "harness": HARNESS, "recipient_key_id": recipient_key_id}, sort_keys=True, separators=(",", ":")).encode()


def decrypt(envelope: dict, private_raw: bytes, run_id: str) -> bytes:
    required = {"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(envelope) != required:
        raise RuntimeError("P570 envelope field-set mismatch")
    if envelope["schema"] != SCHEMA or str(envelope["run_id"]) != str(run_id):
        raise RuntimeError("P570 envelope run identity mismatch")
    if envelope["authority"] != "research_only" or envelope["harness"] != HARNESS:
        raise RuntimeError("P570 envelope authority/harness mismatch")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    expected = key_id(recipient_raw)
    if envelope["recipient_key_id"] != expected:
        raise RuntimeError("P570 recipient fingerprint mismatch")
    sender_raw = b64d(envelope["sender_public_b64"])
    nonce = b64d(envelope["nonce_b64"])
    ciphertext = b64d(envelope["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("P570 sender/nonce shape invalid")
    ad = aad(run_id, expected)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(ad).digest(), info=INFO).derive(shared)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, ad)
    if hashlib.sha256(plaintext).hexdigest() != envelope["plaintext_sha256"]:
        raise RuntimeError("P570 plaintext digest mismatch")
    return plaintext


def extract(payload: bytes, root: Path) -> dict:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tf:
        members = tf.getmembers()
        names = {m.name for m in members if m.isfile()}
        expected = {"payload-manifest.json", *ALLOWED_FILES}
        if names != expected:
            raise RuntimeError(f"P570 payload file-set mismatch: {sorted(names ^ expected)}")
        for m in members:
            if not m.isfile():
                continue
            rel = Path(m.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("unsafe P570 payload path")
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            if src is None:
                raise RuntimeError(f"unable to extract {m.name}")
            target.write_bytes(src.read())
    manifest = json.loads((root / "payload-manifest.json").read_text())
    if manifest.get("schema") != PAYLOAD_SCHEMA or manifest.get("harness") != HARNESS:
        raise RuntimeError("P570 payload manifest identity mismatch")
    hashes_expected = manifest.get("files") or {}
    if set(hashes_expected) != ALLOWED_FILES:
        raise RuntimeError("P570 manifest file-set mismatch")
    for rel, expected in hashes_expected.items():
        actual = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"P570 source digest mismatch: {rel}")
    return manifest


def consume(envelope_path: Path, private_key_path: Path, run_id: str, receipt_path: Path) -> dict:
    env = json.loads(envelope_path.read_text())
    private_raw = b64d(private_key_path.read_text().strip())
    if len(private_raw) != 32:
        raise RuntimeError("P570 recipient private key invalid")
    payload = decrypt(env, private_raw, run_id)
    with tempfile.TemporaryDirectory(prefix="p570-") as td:
        root = Path(td)
        manifest = extract(payload, root)
        run_env = dict(os.environ)
        run_env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [sys.executable, "-m", "research.run_p570_p06_rare_marginal_tilt_20260911"],
            cwd=root,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1800,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"P570 private harness failed rc={proc.returncode}")
        result_path = root / RESULT
        if not result_path.is_file():
            raise RuntimeError("P570 private result missing")
        result_bytes = result_path.read_bytes()
        result = json.loads(result_bytes)
        comparison = result["comparison"]
        support = result["support"]
        policies = result["policies"]
        receipt = {
            "schema": "p570-p06-public-compute-receipt-v1",
            "run_id": str(run_id),
            "authority": "research_only",
            "harness": HARNESS,
            "classification": result["classification"],
            "rare_annualized_return": policies["rare_marginal_tilt"]["annualized_return"],
            "equal_supported_annualized_return": policies["equal_supported"]["annualized_return"],
            "annualized_excess_vs_equal_supported": comparison["annualized_excess_vs_equal_supported"],
            "positive_incremental_folds": comparison["positive_incremental_folds"],
            "fold_count": comparison["fold_count"],
            "binding_scarcity_weekly_decisions": support["binding_scarcity_weekly_decisions"],
            "rare_tilt_count": support["rare_tilt_count"],
            "prior_spread_burnin": support["prior_spread_burnin"],
            "prior_spread_quantile": support["prior_spread_quantile"],
            "opportunity_rows": support["opportunity_rows"],
            "weekly_rows": support["weekly_rows"],
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "payload_plaintext_sha256": env["plaintext_sha256"],
            "source_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "private_stdout_exposed": False,
            "private_stderr_exposed": False,
            "private_source_persisted": False,
            "full_decisions_persisted_publicly": False,
        }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--receipt", required=True)
    args = p.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id, Path(args.receipt))
    print("P570_PUBLIC_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
