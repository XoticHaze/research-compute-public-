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
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "forward-native-ephemeral-x25519-v1"
RETURN_SCHEMA = "forward-native-return-x25519-v1"
PAYLOAD_SCHEMA = "foundry.forward_native_source_payload.v1"
INFO = b"research-foundry-forward-native-ephemeral-v1"
RETURN_INFO = b"research-foundry-forward-native-return-v1"

HARNESS_SPECS: dict[str, dict[str, Any]] = {
    "semiconductor_shared_ridge_three_book_v1": {
        "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
        "source_ref": "e73ec9b15180e208de541ce5d5304888e5550433",
        "files": {
            "research/semiconductor_external_forward_standalone_20260910.py",
            "research/semiconductor_three_book_forward_contract_20260910.json",
            "research/semiconductor_three_book_forward_20260910.py",
        },
    },
    "homebuilders_adaptive_duration_v1": {
        "program_id": "HOMEBUILDERS",
        "source_ref": "b2f933b57efbbf4297620492aa415d0fcd2f613c",
        "files": {
            "research/run_homebuilders_adaptive_duration_forward_20260905.py",
            "research/run_homebuilders_forward_observer_20260902.py",
            "research/run_industry_generic_entry_transport_20260902.py",
            "research/run_entry_cross_sector_reverse_transfer_20260902.py",
            "research/run_survivor_entry_value_20260902.py",
            "research/run_survivor_fixed10_vs20_capital_20260902.py",
            "research/homebuilders_adaptive_duration_forward_contract_20260905.json",
            "research/homebuilders_forward_observer_contract_20260902.json",
        },
    },
    "generalized_largecap_ridge_v1": {
        "program_id": "GENERALIZED_LARGECAP_RIDGE",
        "source_ref": "6449c2e7f2898ad5198bba5101da17543b4490c1",
        "files": {
            "research/run_generalized_largecap_forward_snapshot_20260902.py",
            "research/run_semiconductor_external_forward_snapshot_20260902.py",
        },
    },
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _key_id(raw: bytes) -> str:
    return "sha256:" + _sha(raw)


def _aad(schema: str, run_id: str, harness: str, recipient_key_id: str) -> bytes:
    return json.dumps({
        "schema": schema,
        "run_id": str(run_id),
        "authority": "research_only",
        "harness": harness,
        "recipient_key_id": recipient_key_id,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _derive(shared: bytes, aad: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=info).derive(shared)


def _decrypt_input(envelope: dict, private_raw: bytes, run_id: str, harness: str) -> bytes:
    required = {
        "schema", "run_id", "authority", "harness", "recipient_key_id",
        "sender_public_b64", "nonce_b64", "ciphertext_b64", "plaintext_sha256",
    }
    if set(envelope) != required:
        raise RuntimeError("input envelope field-set mismatch")
    if envelope["schema"] != SCHEMA or str(envelope["run_id"]) != str(run_id):
        raise RuntimeError("input run identity mismatch")
    if envelope["authority"] != "research_only" or envelope["harness"] != harness:
        raise RuntimeError("input authority/harness mismatch")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    expected_id = _key_id(recipient_raw)
    if envelope["recipient_key_id"] != expected_id:
        raise RuntimeError("input recipient fingerprint mismatch")
    sender_raw = _b64d(envelope["sender_public_b64"])
    nonce = _b64d(envelope["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("input key/nonce shape invalid")
    aad = _aad(SCHEMA, run_id, harness, expected_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad, INFO)).decrypt(nonce, _b64d(envelope["ciphertext_b64"]), aad)
    if _sha(plaintext) != envelope["plaintext_sha256"]:
        raise RuntimeError("input plaintext digest mismatch")
    return plaintext


def _safe_extract(payload: bytes, root: Path, harness: str) -> dict:
    spec = HARNESS_SPECS[harness]
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tf:
        members = tf.getmembers()
        names = {m.name for m in members if m.isfile()}
        expected = {"payload-manifest.json", *spec["files"]}
        if names != expected:
            raise RuntimeError(f"payload file-set mismatch: {sorted(names ^ expected)}")
        for member in members:
            if not member.isfile():
                continue
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("unsafe payload path")
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError(f"unable to read {member.name}")
            target.write_bytes(src.read())
    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PAYLOAD_SCHEMA or manifest.get("harness") != harness:
        raise RuntimeError("payload manifest identity mismatch")
    if manifest.get("program_id") != spec["program_id"] or manifest.get("source_ref") != spec["source_ref"]:
        raise RuntimeError("payload frozen source identity mismatch")
    hashes_expected = manifest.get("files") or {}
    if set(hashes_expected) != set(spec["files"]):
        raise RuntimeError("payload manifest file-set mismatch")
    for rel, expected_hash in hashes_expected.items():
        if _sha((root / rel).read_bytes()) != expected_hash:
            raise RuntimeError(f"payload digest mismatch: {rel}")
    return manifest


def _run(cmd: list[str], root: Path, timeout: int = 1200) -> None:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
    if run.returncode != 0:
        raise RuntimeError(f"private native harness failed rc={run.returncode}")


def _execute(root: Path, harness: str, adapter_script: Path) -> tuple[Path, Path | None, Path]:
    spec = HARNESS_SPECS[harness]
    adapter = root / "artifacts" / f"forward_program_adapter_{spec['program_id'].lower()}.json"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    if harness == "semiconductor_shared_ridge_three_book_v1":
        native = root / "research/results/semiconductor_external_forward/current.json"
        native.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "research.semiconductor_external_forward_standalone_20260910", "--output", str(native.relative_to(root))], root)
        prediction = json.loads(native.read_text(encoding="utf-8"))
        generation = str(prediction["generation_bar_date"])
        contract = json.loads((root / "research/semiconductor_three_book_forward_contract_20260910.json").read_text(encoding="utf-8"))
        book: Path | None = None
        if generation >= str(contract["prospective_start_signal_date"]):
            book = root / "research/results/semiconductor_three_book_forward" / f"{generation}.json"
            book.parent.mkdir(parents=True, exist_ok=True)
            _run([
                sys.executable, "-m", "research.semiconductor_three_book_forward_20260910",
                "--prediction", str(native.relative_to(root)),
                "--contract", "research/semiconductor_three_book_forward_contract_20260910.json",
                "--output", str(book.relative_to(root)),
            ], root)
        cmd = [sys.executable, str(adapter_script), "--program", "SEMICONDUCTOR_SHARED_RIDGE", "--input", str(native), "--output", str(adapter)]
        if book is not None:
            cmd.extend(["--book", str(book)])
        _run(cmd, root)
        return native, book, adapter
    if harness == "homebuilders_adaptive_duration_v1":
        native = root / "research/results/homebuilders_adaptive_duration_forward_20260905.json"
        native.parent.mkdir(parents=True, exist_ok=True)
        _run([
            sys.executable, "-m", "research.run_homebuilders_adaptive_duration_forward_20260905",
            "--contract", "research/homebuilders_adaptive_duration_forward_contract_20260905.json",
            "--output", str(native.relative_to(root)),
        ], root)
        _run([sys.executable, str(adapter_script), "--program", "HOMEBUILDERS", "--input", str(native), "--output", str(adapter)], root)
        return native, None, adapter
    if harness == "generalized_largecap_ridge_v1":
        native = root / "research/results/generalized_largecap_forward_snapshot_20260902.json"
        native.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "research.run_generalized_largecap_forward_snapshot_20260902"], root)
        _run([sys.executable, str(adapter_script), "--program", "GENERALIZED_LARGECAP_RIDGE", "--input", str(native), "--output", str(adapter)], root)
        return native, None, adapter
    raise RuntimeError(f"unsupported harness {harness}")


def _return_tar(native: Path, book: Path | None, adapter: Path, receipt: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT) as tf:
        for name, path in (("native.json", native), ("paper-book.json", book), ("adapter.json", adapter)):
            if path is None:
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            tf.addfile(info, io.BytesIO(data))
        data = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
        info = tarfile.TarInfo("receipt.json")
        info.size = len(data)
        info.mtime = 0
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _encrypt_return(payload: bytes, manifest: dict, run_id: str, harness: str) -> dict:
    recipient_raw = _b64d(str(manifest["return_recipient_b64"]))
    if len(recipient_raw) != 32:
        raise RuntimeError("return recipient invalid")
    key_id = _key_id(recipient_raw)
    if manifest.get("return_recipient_key_id") != key_id:
        raise RuntimeError("return recipient fingerprint mismatch")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aad = _aad(RETURN_SCHEMA, run_id, harness, key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(_derive(shared, aad, RETURN_INFO)).encrypt(nonce, payload, aad)
    return {
        "schema": RETURN_SCHEMA,
        "run_id": str(run_id),
        "authority": "research_only",
        "harness": harness,
        "recipient_key_id": key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_sha256": _sha(payload),
    }


def consume(envelope_path: Path, private_key_path: Path, run_id: str, harness: str, adapter_script: Path, output: Path) -> dict:
    if harness not in HARNESS_SPECS:
        raise RuntimeError(f"unsupported harness {harness}")
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("input recipient private key invalid")
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    plaintext = _decrypt_input(envelope, private_raw, run_id, harness)
    with tempfile.TemporaryDirectory(prefix="forward-native-") as td:
        root = Path(td)
        manifest = _safe_extract(plaintext, root, harness)
        native, book, adapter = _execute(root, harness, adapter_script)
        receipt = {
            "schema": "forward-native-public-compute-receipt-v1",
            "authority": "research_only",
            "harness": harness,
            "program_id": HARNESS_SPECS[harness]["program_id"],
            "source_ref": HARNESS_SPECS[harness]["source_ref"],
            "native_sha256": _sha(native.read_bytes()),
            "adapter_sha256": _sha(adapter.read_bytes()),
            "book_sha256": _sha(book.read_bytes()) if book and book.is_file() else None,
            "private_source_persisted": False,
            "private_stdout_exposed": False,
            "private_stderr_exposed": False,
        }
        payload = _return_tar(native, book, adapter, receipt)
        output.write_text(json.dumps(_encrypt_return(payload, manifest, run_id, harness), sort_keys=True) + "\n", encoding="utf-8")
        return receipt


def self_test() -> None:
    assert set(HARNESS_SPECS) == {
        "semiconductor_shared_ridge_three_book_v1",
        "homebuilders_adaptive_duration_v1",
        "generalized_largecap_ridge_v1",
    }
    assert HARNESS_SPECS["homebuilders_adaptive_duration_v1"]["source_ref"] == "b2f933b57efbbf4297620492aa415d0fcd2f613c"
    assert "research/run_homebuilders_adaptive_duration_forward_20260905.py" in HARNESS_SPECS["homebuilders_adaptive_duration_v1"]["files"]
    assert HARNESS_SPECS["generalized_largecap_ridge_v1"]["program_id"] == "GENERALIZED_LARGECAP_RIDGE"
    print("FORWARD_NATIVE_EPHEMERAL_CONSUMER_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope")
    p.add_argument("--private-key")
    p.add_argument("--run-id")
    p.add_argument("--harness")
    p.add_argument("--adapter-script", default="research/forward_native_program_adapter_r1.py")
    p.add_argument("--return-envelope")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.envelope, args.private_key, args.run_id, args.harness, args.return_envelope)):
        p.error("live consume requires envelope, private-key, run-id, harness and return-envelope")
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id, args.harness, Path(args.adapter_script).resolve(), Path(args.return_envelope))
    print("FORWARD_NATIVE_PUBLIC_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
