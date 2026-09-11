from __future__ import annotations

"""Fixed private-input acceptance for MM #504 forward identity evidence."""

import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mm-survivor-forward-identity-x25519-v1"
HARNESS = "mm_survivor_forward_identity_private_acceptance_v1"
INFO = b"commandcenter-mm-survivor-forward-identity-v1"
EXPECTED_MM_COMMIT = "7525295980af51dcdffe3dd222bf5e89923e9108"
EXPECTED_GIT_BLOBS = {
    "strategy_forward_identity_evidence.py": "2a6d00372328aa599fe83aba781b2223956791d6",
    "strategy_health_preview_binding.py": "92f76e2648418f0aa15d1493b797cfa5e8014c1e",
}
FILES = set(EXPECTED_GIT_BLOBS)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha1(raw: bytes) -> str:
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
        if set(tf.getnames()) != FILES | {"payload_manifest.json"}:
            raise RuntimeError("private payload file set mismatch")
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root_resolved not in target.parents or not member.isfile():
                raise RuntimeError("unsafe private archive member")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest = json.loads((root / "payload_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "mm.survivor_forward_identity_acceptance_payload.v1":
        raise RuntimeError("private payload schema mismatch")
    if manifest.get("harness") != HARNESS or manifest.get("mm_commit") != EXPECTED_MM_COMMIT:
        raise RuntimeError("private payload identity mismatch")
    digests = manifest.get("files") or {}
    if set(digests) != FILES:
        raise RuntimeError("private payload manifest file set mismatch")
    for rel, digest in digests.items():
        raw = (root / rel).read_bytes()
        if sha256_bytes(raw) != digest:
            raise RuntimeError(f"private payload inner digest mismatch: {rel}")
        if git_blob_sha1(raw) != EXPECTED_GIT_BLOBS[rel]:
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
        local = response_dir / Path(str(item.get("path") or "")).name
        raw = local.read_bytes()
        if sha256_bytes(raw) != str(item.get("sha256") or ""):
            raise RuntimeError("encrypted chunk digest mismatch")
        text = raw.decode("ascii")
        if len(text) != int(item.get("chars") or -1):
            raise RuntimeError("encrypted chunk length mismatch")
        encoded_parts.append(text)
    ciphertext = b64d("".join(encoded_parts))
    if sha256_bytes(ciphertext) != str(env.get("ciphertext_sha256") or ""):
        raise RuntimeError("encrypted ciphertext digest mismatch")
    return ciphertext


def verify_behavior(module_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("identity_evidence_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    complete = module.project_forward_identity_evidence({
        "strategy_id": "crw_score_multi_mode", "symbol": "MNQ", "timeframe": "12Min",
        "strategy_spec_digest": "digest", "runtime_id": "runtime",
    })
    if complete.get("state") != "IDENTITY_ATTRIBUTABLE" or complete.get("clean_confirmation_identity_eligible") is not True:
        raise RuntimeError("complete identity did not become attributable")
    missing = module.project_forward_identity_evidence({
        "strategy_id": "crw_score_multi_mode", "symbol": "AMAT", "timeframe": "15Min",
        "runtime_id": "crw_amat_15m_selected",
    })
    if missing.get("state") != "EVIDENCE_INCOMPLETE" or missing.get("clean_confirmation_identity_eligible") is not False:
        raise RuntimeError("missing digest did not fail closed")
    if missing.get("missing") != ["strategy_spec_digest"]:
        raise RuntimeError("missing digest attribution mismatch")
    malformed = module.project_forward_identity_evidence({
        "strategy_id": "crw_score_multi_mode", "symbol": "APH", "timeframe": "15Min",
        "strategy_spec_digest": "digest", "runtime_identity": "unexpected",
    })
    if "runtime_id" not in malformed.get("missing", []):
        raise RuntimeError("malformed nested runtime identity did not fail closed")


def verify_binding(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = assigned = called = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "strategy_forward_identity_evidence":
            imported = imported or any(alias.name == "project_forward_identity_evidence" for alias in node.names)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == "forward_identity_evidence":
            assigned = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "project_forward_identity_evidence":
            called = True
    if not (imported and assigned and called):
        raise RuntimeError("Strategy Health binding does not expose forward identity evidence")


def consume(envelope_path: Path, response_dir: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {"schema", "run_id", "harness", "mm_commit", "recipient_key_id", "sender_public_b64", "nonce_b64", "ciphertext_sha256", "plaintext_sha256", "chunks"}
    if set(env) != required:
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env["harness"] != HARNESS or env["mm_commit"] != EXPECTED_MM_COMMIT:
        raise RuntimeError("envelope harness/MM commit mismatch")

    private = x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text(encoding="ascii").strip()))
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
    plaintext = ChaCha20Poly1305(derive(shared, associated)).decrypt(nonce, load_ciphertext(env, response_dir), associated)
    if sha256_bytes(plaintext) != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = extract_and_verify(plaintext, root)
        compile_ok = True
        for rel in FILES:
            try:
                compile((root / rel).read_text(encoding="utf-8"), rel, "exec")
            except Exception:
                compile_ok = False
        verify_behavior(root / "strategy_forward_identity_evidence.py")
        verify_binding(root / "strategy_health_preview_binding.py")

    return {
        "schema": "mm-survivor-forward-identity-acceptance-receipt-v2",
        "authority": "private_mm_source_validation_only",
        "harness": HARNESS,
        "mm_commit": manifest["mm_commit"],
        "status": "PASS" if compile_ok else "FAIL",
        "checks": {
            "reviewed_source_blob_identity_verified": True,
            "private_modules_compile": compile_ok,
            "identity_behavior_fail_closed": True,
            "strategy_health_binding_present": True,
        },
        "reviewed_source_blob_count": len(EXPECTED_GIT_BLOBS),
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
    receipt = consume(Path(args.envelope), Path(args.response_dir), Path(args.private_key), args.run_id)
    print("MM_SURVIVOR_FORWARD_IDENTITY_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
