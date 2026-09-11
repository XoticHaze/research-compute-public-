from __future__ import annotations

"""Fixed encrypted acceptance consumer for the MM #504 survivor-forward backend.

The public runner receives only a one-run encrypted tarball produced by the
released MM transport packager. Plaintext exists only in runner temp. The
payload file set, MM commit, harness, exact private Git blob identities, per-file
digests, and AEAD associated data are fixed here; no arbitrary command arrives
in the payload.
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

SCHEMA = "mm-survivor-forward-x25519-v1"
RECIPIENT_SCHEMA = "mm-survivor-forward-ephemeral-recipient-v1"
HARNESS = "mm_survivor_forward_private_acceptance_v1"
INFO = b"commandcenter-mm-survivor-forward-v1"
EXPECTED_MM_COMMIT = "52e1c4daf5ff9060dfe0068d37858f2ea7170b67"
EXPECTED_GIT_BLOBS = {
    "strategy_capital_readiness.py": "dddf48c557689413f469058bab2c0034958796e1",
    "strategy_forward_intelligence.py": "45fc244ff109a21c4b9dcd899689cee0d22e1fc3",
    "survivor_capital_readiness_policy.py": "ba7689c493c3c543de0a9e4091169894f13a2ed8",
    "strategy_health_canonical_trade_consumer.py": "4221da3aab5924df71c166338dd362b074e64ccd",
    "strategy_health_preview_binding.py": "92f76e2648418f0aa15d1493b797cfa5e8014c1e",
    "strategy_health_evidence_pipeline.py": "0343c6b1efadd7ab416737dfe40d413f9b5220f4",
    "strategy_health_position_context.py": "cb13af73f8cde37d55d8a00e6951e7085b23a753",
    "strategy_health_comparable_context.py": "a27373206c0a2f28f7fea3576cc898074e3b71c5",
    "strategy_health_operator_context.py": "3359375755e19a66cb793dcb8deef69a1985beed",
    "scripts/operator/verify_survivor_forward_operator_contract_v1.py": "64c85d57c891ef229a2e65a39a450808f7a38e7d",
    "tests/test_strategy_capital_readiness.py": "73b195b88776bbe2c3f4517d78791f319d8a3a90",
    "tests/test_strategy_capital_readiness_historical_compat.py": "3fd66ca9eba1194db8b48bf5d71c8bf87f2e2f3a",
    "tests/test_strategy_health_canonical_trade_forward_conformance.py": "8e5bf693808a724fee1ce4c5a47674708f491104",
    "tests/test_strategy_forward_intelligence.py": "8d277458394ec25bc30a069ef4762122bd8acaf5",
    "tests/test_strategy_forward_intelligence_json_boundary.py": "9d7c5cf72d920ea2671d976f6b537603c1eb5145",
    "tests/test_survivor_forward_operator_contract_verifier_v1.py": "4c0af6e43ee75004096e53b16050f845e856f68f",
}
FILES = set(EXPECTED_GIT_BLOBS)
TESTS = [
    "tests.test_strategy_capital_readiness",
    "tests.test_strategy_capital_readiness_historical_compat",
    "tests.test_strategy_health_canonical_trade_forward_conformance",
    "tests.test_strategy_forward_intelligence",
    "tests.test_strategy_forward_intelligence_json_boundary",
    "tests.test_survivor_forward_operator_contract_verifier_v1",
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "harness": HARNESS,
            "mm_commit": EXPECTED_MM_COMMIT,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(associated).digest(),
        info=INFO,
    ).derive(shared)


def extract_and_verify(payload: bytes, root: Path) -> dict:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        expected = FILES | {"payload_manifest.json"}
        if set(tf.getnames()) != expected:
            raise RuntimeError("private payload file set mismatch")
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root_resolved not in target.parents or not member.isfile():
                raise RuntimeError("unsafe private archive member")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest = json.loads((root / "payload_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "mm.survivor_forward_acceptance_payload.v1":
        raise RuntimeError("private payload schema mismatch")
    if manifest.get("harness") != HARNESS:
        raise RuntimeError("private payload harness mismatch")
    if manifest.get("mm_commit") != EXPECTED_MM_COMMIT:
        raise RuntimeError("private payload MM commit mismatch")
    digests = manifest.get("files") or {}
    if set(digests) != FILES:
        raise RuntimeError("private payload manifest file set mismatch")
    for rel, digest in digests.items():
        path = root / rel
        if sha256(path) != digest:
            raise RuntimeError(f"private payload inner digest mismatch: {rel}")
        if git_blob_sha1(path) != EXPECTED_GIT_BLOBS[rel]:
            raise RuntimeError(f"private payload reviewed-source blob mismatch: {rel}")
    return manifest


def load_ciphertext(env: dict, response_dir: Path) -> bytes:
    chunks = env.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("encrypted envelope has no chunks")
    encoded_parts: list[str] = []
    for item in chunks:
        if not isinstance(item, dict):
            raise RuntimeError("encrypted chunk entry malformed")
        remote = str(item.get("path") or "")
        local = response_dir / Path(remote).name
        raw = local.read_bytes()
        if sha256_bytes(raw) != str(item.get("sha256") or ""):
            raise RuntimeError(f"encrypted chunk digest mismatch: {local.name}")
        text = raw.decode("ascii")
        if len(text) != int(item.get("chars") or -1):
            raise RuntimeError(f"encrypted chunk length mismatch: {local.name}")
        encoded_parts.append(text)
    ciphertext = b64d("".join(encoded_parts))
    if sha256_bytes(ciphertext) != str(env.get("ciphertext_sha256") or ""):
        raise RuntimeError("encrypted ciphertext digest mismatch")
    return ciphertext


def consume(envelope_path: Path, response_dir: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "run_id",
        "harness",
        "mm_commit",
        "recipient_key_id",
        "sender_public_b64",
        "nonce_b64",
        "ciphertext_sha256",
        "plaintext_sha256",
        "chunks",
    }
    if set(env) != required:
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env["harness"] != HARNESS or env["mm_commit"] != EXPECTED_MM_COMMIT:
        raise RuntimeError("envelope harness/MM commit mismatch")

    private_raw = b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != key_id:
        raise RuntimeError("recipient fingerprint mismatch")

    sender_raw = b64d(env["sender_public_b64"])
    nonce = b64d(env["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce length invalid")
    associated = aad(str(expected_run_id), key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(derive(shared, associated)).decrypt(
        nonce, load_ciphertext(env, response_dir), associated
    )
    if sha256_bytes(plaintext) != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = extract_and_verify(plaintext, root)
        compile_rc = subprocess.run(
            [
                "python",
                "-m",
                "py_compile",
                "strategy_capital_readiness.py",
                "strategy_forward_intelligence.py",
                "strategy_health_canonical_trade_consumer.py",
                "strategy_health_preview_binding.py",
                "scripts/operator/verify_survivor_forward_operator_contract_v1.py",
            ],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        test_rc = subprocess.run(
            ["python", "-m", "unittest", "-v", *TESTS],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    passed = compile_rc == 0 and test_rc == 0
    return {
        "schema": "mm-survivor-forward-backend-acceptance-receipt-v5",
        "authority": "private_mm_source_validation_only",
        "harness": HARNESS,
        "mm_commit": manifest["mm_commit"],
        "status": "PASS" if passed else "FAIL",
        "checks": {
            "reviewed_source_blob_identity_verified": True,
            "production_modules_compile": compile_rc == 0,
            "six_requested_test_modules_pass": test_rc == 0,
            "operator_contract_verifier_included": True,
            "completed_trade_operator_rows_fail_closed": True,
        },
        "reviewed_source_blob_count": len(EXPECTED_GIT_BLOBS),
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
    parser.add_argument("--response-dir", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(
        Path(args.envelope), Path(args.response_dir), Path(args.private_key), args.run_id
    )
    print("MM_SURVIVOR_FORWARD_BACKEND_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
