from __future__ import annotations

"""Decrypt and build one exact MM ui-react tree on public compute.

The consumer accepts only a payload whose reconstructed Git tree equals the
hard-pinned private MM ui-react tree. It installs the pinned lockfile with
lifecycle scripts disabled, executes Vite directly, and emits only a sanitized
receipt. Plaintext remains in runner temp.
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mm-ui-react-build-x25519-v1"
HARNESS = "mm_ui_react_private_build_v1"
INFO = b"commandcenter-mm-ui-react-build-v1"
EXPECTED_MM_COMMIT = "9233d5a0c8ab7827775208c602e00d0f7fac758a"
EXPECTED_UI_TREE = "5c80832732ed0299f29faf15dcf5d237c097ad3d"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "harness": HARNESS,
            "mm_commit": EXPECTED_MM_COMMIT,
            "ui_tree_sha": EXPECTED_UI_TREE,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def derive(shared: bytes, associated: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=hashlib.sha256(associated).digest(), info=INFO,
    ).derive(shared)


def load_ciphertext(env: dict, response_dir: Path) -> bytes:
    chunks = env.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("encrypted envelope has no chunks")
    encoded: list[str] = []
    for item in chunks:
        if not isinstance(item, dict):
            raise RuntimeError("encrypted chunk entry malformed")
        remote = str(item.get("path") or "")
        if not remote.startswith(f"rendezvous/responses/{env['run_id']}/") or not remote.endswith(".b64"):
            raise RuntimeError("unsafe encrypted chunk path")
        local = response_dir / Path(remote).name
        raw = local.read_bytes()
        if sha256_bytes(raw) != str(item.get("sha256") or ""):
            raise RuntimeError("encrypted chunk digest mismatch")
        text = raw.decode("ascii")
        if len(text) != int(item.get("chars") or -1):
            raise RuntimeError("encrypted chunk length mismatch")
        encoded.append(text)
    cipher = b64d("".join(encoded))
    if sha256_bytes(cipher) != str(env.get("ciphertext_sha256") or ""):
        raise RuntimeError("ciphertext digest mismatch")
    return cipher


def extract_verified(payload: bytes, root: Path) -> Path:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        if "payload_manifest.json" not in names:
            raise RuntimeError("payload manifest missing")
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if target != root_resolved and root_resolved not in target.parents:
                raise RuntimeError("unsafe archive path")
            if not member.isfile():
                raise RuntimeError("payload contains non-file member")
            if member.name != "payload_manifest.json" and not member.name.startswith("ui-react/"):
                raise RuntimeError("payload contains non-ui file")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest = json.loads((root / "payload_manifest.json").read_text(encoding="utf-8"))
    if manifest != {
        "schema": "mm.ui_react_build_payload.v1",
        "mm_commit": EXPECTED_MM_COMMIT,
        "ui_tree_sha": EXPECTED_UI_TREE,
        "harness": HARNESS,
        "file_count": len([n for n in names if n.startswith("ui-react/")]),
    }:
        raise RuntimeError("payload manifest mismatch")

    ui = root / "ui-react"
    if not (ui / "package.json").is_file() or not (ui / "package-lock.json").is_file():
        raise RuntimeError("package metadata missing")
    subprocess.run(["git", "init", "-q"], cwd=ui, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "-A", "-f"], cwd=ui, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tree_sha = subprocess.check_output(["git", "write-tree"], cwd=ui, text=True).strip()
    if tree_sha != EXPECTED_UI_TREE:
        raise RuntimeError("private ui tree identity mismatch")
    return ui


def dist_digest(dist: Path) -> tuple[str, int]:
    files = sorted(p for p in dist.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(dist).as_posix().encode("utf-8")
        raw = path.read_bytes()
        h.update(len(rel).to_bytes(4, "big")); h.update(rel)
        h.update(len(raw).to_bytes(8, "big")); h.update(raw)
    return h.hexdigest(), len(files)


def consume(envelope: Path, response_dir: Path, private_key: Path, run_id: str) -> dict:
    env = json.loads(envelope.read_text(encoding="utf-8"))
    required = {
        "schema", "run_id", "harness", "mm_commit", "ui_tree_sha",
        "recipient_key_id", "sender_public_b64", "nonce_b64",
        "ciphertext_sha256", "plaintext_sha256", "chunks",
    }
    if set(env) != required:
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(run_id):
        raise RuntimeError("envelope run/schema mismatch")
    if env["harness"] != HARNESS or env["mm_commit"] != EXPECTED_MM_COMMIT or env["ui_tree_sha"] != EXPECTED_UI_TREE:
        raise RuntimeError("envelope source identity mismatch")

    private_raw = b64d(private_key.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != key_id:
        raise RuntimeError("recipient fingerprint mismatch")
    sender_raw = b64d(env["sender_public_b64"])
    nonce = b64d(env["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("sender key/nonce length invalid")
    associated = aad(str(run_id), key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plain = ChaCha20Poly1305(derive(shared, associated)).decrypt(
        nonce, load_ciphertext(env, response_dir), associated
    )
    if sha256_bytes(plain) != env["plaintext_sha256"]:
        raise RuntimeError("plaintext digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        ui = extract_verified(plain, Path(td))
        package = json.loads((ui / "package.json").read_text(encoding="utf-8"))
        scripts = package.get("scripts") or {}
        if scripts.get("build") != "vite build" or "prebuild" in scripts or "postbuild" in scripts:
            raise RuntimeError("unexpected production build script contract")
        lock = json.loads((ui / "package-lock.json").read_text(encoding="utf-8"))
        if lock.get("lockfileVersion") != 3:
            raise RuntimeError("unexpected npm lockfile version")
        install = subprocess.run(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=ui, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        build = subprocess.run(
            [str(ui / "node_modules" / ".bin" / "vite"), "build"],
            cwd=ui, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ) if install.returncode == 0 else None
        dist = ui / "dist"
        passed = install.returncode == 0 and build is not None and build.returncode == 0 and (dist / "index.html").is_file()
        digest, count = dist_digest(dist) if passed else (None, 0)

    return {
        "schema": "mm-ui-react-production-build-receipt-v1",
        "authority": "private_mm_ui_build_validation_only",
        "harness": HARNESS,
        "mm_commit": EXPECTED_MM_COMMIT,
        "ui_tree_sha": EXPECTED_UI_TREE,
        "status": "PASS" if passed else "FAIL",
        "checks": {
            "exact_private_ui_tree": True,
            "npm_ci_ignore_scripts": install.returncode == 0,
            "vite_production_build": bool(build is not None and build.returncode == 0),
            "dist_index_present": bool(passed),
        },
        "dist_file_count": count,
        "dist_digest_sha256": digest,
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
    print("MM_UI_REACT_BUILD_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
