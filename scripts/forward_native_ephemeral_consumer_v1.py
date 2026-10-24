from __future__ import annotations

import argparse
import base64
import gzip
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
MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
MAX_PLAINTEXT_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_TOTAL_MEMBER_BYTES = 4 * 1024 * 1024
MAX_TAR_MEMBERS = 32
MAX_UNCOMPRESSED_TAR_BYTES = 8 * 1024 * 1024


class _PublicSafeArgumentParser(argparse.ArgumentParser):
    """No private CLI values or filenames in public Actions stderr."""
    def error(self, _message):
        raise ValueError("invalid_public_cli_arguments")

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


_PUBLIC_KEYS = frozenset({
    "schema", "authority", "harness", "program_id", "source_ref",
    "native_sha256", "adapter_sha256", "book_sha256",
    "private_source_persisted", "private_stdout_exposed", "private_stderr_exposed",
})
_PUBLIC_FALSE = ("private_source_persisted", "private_stdout_exposed", "private_stderr_exposed")


def public_receipt(value: dict) -> dict:
    """Fixed public success projection; never forward nested native result fields."""
    if not isinstance(value, dict) or set(value) != _PUBLIC_KEYS:
        raise RuntimeError("PUBLIC_RECEIPT_FIELD_SET_REJECTED")
    spec = HARNESS_SPECS.get(value.get("harness"))
    if (not spec or value.get("schema") != "forward-native-public-compute-receipt-v1"
            or value.get("authority") != "research_only"
            or value.get("program_id") != spec["program_id"]
            or value.get("source_ref") != spec["source_ref"]):
        raise RuntimeError("PUBLIC_RECEIPT_IDENTITY_REJECTED")
    if any(value.get(k) is not False for k in _PUBLIC_FALSE):
        raise RuntimeError("PUBLIC_RECEIPT_AUTHORITY_REJECTED")
    for key in ("native_sha256", "adapter_sha256", "book_sha256"):
        digest = value.get(key)
        if digest is None and key == "book_sha256":
            continue
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RuntimeError("PUBLIC_RECEIPT_DIGEST_REJECTED")
    return {key: value[key] for key in sorted(_PUBLIC_KEYS)}


def public_rejection() -> None:
    """Constant public failure, independent of encrypted input and caller strings."""
    print("FORWARD_NATIVE_PUBLIC_RECEIPT=" + json.dumps({
        "schema": "forward-native-public-compute-receipt-v1", "status": "REJECTED",
    }, sort_keys=True))


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
    if len(plaintext) > MAX_PLAINTEXT_BYTES or _sha(plaintext) != envelope["plaintext_sha256"]:
        raise RuntimeError("input plaintext size/digest mismatch")
    return plaintext


def _safe_extract(payload: bytes, root: Path, harness: str) -> dict:
    """Bound untrusted tar headers and expansion before writing any source bytes."""
    if len(payload) > MAX_PLAINTEXT_BYTES:
        raise RuntimeError("payload compressed size bound")
    spec = HARNESS_SPECS[harness]
    expected = {"payload-manifest.json", *spec["files"]}
    # gzip/PAX metadata can expand before a tar header is yielded. Bound the
    # entire decompressed archive before tarfile parses any member.
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
        archive_bytes = gz.read(MAX_UNCOMPRESSED_TAR_BYTES + 1)
    if len(archive_bytes) > MAX_UNCOMPRESSED_TAR_BYTES:
        raise RuntimeError("payload gzip expansion bound")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as tf:
        members = []
        seen = set()
        total_bytes = 0
        # Do not call getmembers(): it parses every header before a bound is checked.
        for count, member in enumerate(tf, 1):
            if count > MAX_TAR_MEMBERS:
                raise RuntimeError("payload header count bound")
            if not member.isfile():
                raise RuntimeError("payload unsafe member type")
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts or str(rel) in ("", "."):
                raise RuntimeError("payload unsafe member path")
            canonical = rel.as_posix()
            if canonical in seen:
                raise RuntimeError("payload duplicate member")
            seen.add(canonical)
            if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise RuntimeError("payload individual size bound")
            total_bytes += member.size
            if total_bytes > MAX_TOTAL_MEMBER_BYTES:
                raise RuntimeError("payload aggregate size bound")
            members.append((member, rel))
        if {m.name for m, _ in members} != expected:
            raise RuntimeError("payload file-set mismatch")
        for member, rel in members:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError("payload unreadable member")
            data = src.read(MAX_MEMBER_BYTES + 1)
            if len(data) != member.size:
                raise RuntimeError("payload member size mismatch")
            target.write_bytes(data)
    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PAYLOAD_SCHEMA or manifest.get("harness") != harness:
        raise RuntimeError("payload manifest identity mismatch")
    if manifest.get("program_id") != spec["program_id"] or manifest.get("source_ref") != spec["source_ref"]:
        raise RuntimeError("payload frozen source identity mismatch")
    hashes_expected = manifest.get("files") or {}
    if not isinstance(hashes_expected, dict) or set(hashes_expected) != set(spec["files"]):
        raise RuntimeError("payload manifest file-set mismatch")
    for rel, expected_hash in hashes_expected.items():
        if _sha((root / rel).read_bytes()) != expected_hash:
            raise RuntimeError("payload digest mismatch")
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


def consume(
    envelope_path: Path,
    private_key_path: Path,
    run_id: str,
    harness: str,
    adapter_script: Path,
    output: Path,
    sanitized_adapter_output: Path | None = None,
) -> dict:
    if harness not in HARNESS_SPECS:
        raise RuntimeError(f"unsupported harness {harness}")
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("input recipient private key invalid")
    if envelope_path.stat().st_size > MAX_ENVELOPE_BYTES:
        raise RuntimeError("input envelope size bound")
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    plaintext = _decrypt_input(envelope, private_raw, run_id, harness)
    with tempfile.TemporaryDirectory(prefix="forward-native-") as td:
        root = Path(td)
        manifest = _safe_extract(plaintext, root, harness)
        native, book, adapter = _execute(root, harness, adapter_script)
        if sanitized_adapter_output is not None:
            sanitized_adapter_output.parent.mkdir(parents=True, exist_ok=True)
            sanitized_adapter_output.write_bytes(adapter.read_bytes())
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
    # Synthetic-only, no private model bytes. Verify exact existing tar producer shape.
    spec = HARNESS_SPECS["semiconductor_shared_ridge_three_book_v1"]
    fake = {name: b"synthetic-source" for name in spec["files"]}
    manifest = {
        "schema": PAYLOAD_SCHEMA,
        "harness": "semiconductor_shared_ridge_three_book_v1",
        "program_id": spec["program_id"],
        "source_ref": spec["source_ref"],
        "files": {name: _sha(data) for name, data in fake.items()},
    }
    def pack(entries):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for name, data in entries:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()
    valid = [("payload-manifest.json", json.dumps(manifest).encode())] + list(fake.items())
    with tempfile.TemporaryDirectory() as td:
        parsed = _safe_extract(pack(valid), Path(td), "semiconductor_shared_ridge_three_book_v1")
        assert parsed["source_ref"] == spec["source_ref"]
    bad = [
        (valid + [("payload-manifest.json", b"duplicate")], "payload duplicate member"),
        ([(f"private-sentinel-{i}.txt", b"") for i in range(33)], "payload header count bound"),
        ([("a", b"x" * MAX_MEMBER_BYTES), ("b", b"x" * MAX_MEMBER_BYTES),
          ("c", b"x" * MAX_MEMBER_BYTES)], "payload aggregate size bound"),
        ([("PRIVATE_SENTINEL_DO_NOT_LOG.txt", b"secret")], "payload file-set mismatch"),
        ([("large-gzip-metadata", b"x" * (MAX_UNCOMPRESSED_TAR_BYTES + 1))], "payload gzip expansion bound"),
    ]
    for entries, expected_error in bad:
        with tempfile.TemporaryDirectory() as td:
            try:
                _safe_extract(pack(entries), Path(td), "semiconductor_shared_ridge_three_book_v1")
            except RuntimeError as exc:
                assert str(exc) == expected_error and "SENTINEL" not in str(exc)
            else:
                raise AssertionError("unsafe tar accepted")
    fake_receipt = {
        "schema": "forward-native-public-compute-receipt-v1",
        "authority": "research_only",
        "harness": "semiconductor_shared_ridge_three_book_v1",
        "program_id": spec["program_id"], "source_ref": spec["source_ref"],
        "native_sha256": "a" * 64, "adapter_sha256": "b" * 64,
        "book_sha256": None, "private_source_persisted": False,
        "private_stdout_exposed": False, "private_stderr_exposed": False,
    }
    assert public_receipt(fake_receipt)["harness"] == "semiconductor_shared_ridge_three_book_v1"
    for mutant in ({**fake_receipt, "nested": {"PRIVATE_SENTINEL": "secret"}},
                   {**fake_receipt, "private_stderr_exposed": True}):
        try:
            public_receipt(mutant)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unsafe public receipt accepted")
    check = subprocess.run(
        [sys.executable, __file__, "--harness", "PRIVATE_SENTINEL_DO_NOT_LOG"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
    )
    assert check.returncode == 1 and not check.stderr
    assert "PRIVATE_SENTINEL" not in check.stdout and '"status": "REJECTED"' in check.stdout
    print("FORWARD_NATIVE_PUBLIC_EGRESS_TAR_BOUNDS_SELF_TEST=PASS")
    print("FORWARD_NATIVE_EPHEMERAL_CONSUMER_SELF_TEST=PASS")


def main() -> int:
    try:
        p = _PublicSafeArgumentParser()
        p.add_argument("--envelope")
        p.add_argument("--private-key")
        p.add_argument("--run-id")
        p.add_argument("--harness")
        p.add_argument("--adapter-script", default="research/forward_native_program_adapter_r1.py")
        p.add_argument("--return-envelope")
        p.add_argument("--sanitized-adapter-output")
        p.add_argument("--self-test", action="store_true")
        args = p.parse_args()
        if args.self_test:
            self_test()
            return 0
        if not all((args.envelope, args.private_key, args.run_id, args.harness, args.return_envelope)):
            raise ValueError("missing_required_public_arguments")
        receipt = public_receipt(consume(
            Path(args.envelope), Path(args.private_key), args.run_id, args.harness,
            Path(args.adapter_script).resolve(), Path(args.return_envelope),
            Path(args.sanitized_adapter_output) if args.sanitized_adapter_output else None,
        ))
    except Exception:
        # Never print private tar names, nested model data, paths or tracebacks.
        public_rejection()
        return 1
    print("FORWARD_NATIVE_PUBLIC_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
