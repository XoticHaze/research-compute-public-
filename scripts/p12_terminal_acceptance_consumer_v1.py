from __future__ import annotations

import argparse
import base64
import hashlib
import io
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

SCHEMA = "p12-terminal-acceptance-x25519-v1"
PAYLOAD_SCHEMA = "p12-terminal-acceptance-payload-v1"
RECEIPT_SCHEMA = "p12-terminal-acceptance-receipt-v1"
HARNESS = "mm_p12_reviewed_activation_terminal_acceptance_r4"
AUTHORITY = "product_non_live_acceptance"
MM_HEAD_SHA = "8784628729d92a53889b4b363e7a3c87c0ffff43"
INFO = b"commandcenter-p12-terminal-acceptance-r4"
ENTRYPOINT = "scripts/operator/p12_reviewed_activation_acceptance.py"
MATCHED_REQUEST = "acceptance/matched.json"
MISMATCH_REQUEST = "acceptance/mismatch.json"
MAX_FILES = 96
MAX_PLAINTEXT_BYTES = 12 * 1024 * 1024
MAX_MEMBER_BYTES = 4 * 1024 * 1024


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def aad(run_id: str, key_id: str) -> bytes:
    return canonical_json(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": key_id,
        }
    )


def derive(shared: bytes, associated_data: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(associated_data).digest(),
        info=INFO,
    ).derive(shared)


def safe_member_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "" not in path.parts


def load_json(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    return value


def reject_live_authority(value, prefix: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            child_prefix = f"{prefix}.{key}"
            if normalized in {
                "enable_live_trading",
                "live_trading_enabled",
                "live_enabled",
                "live_unlock",
                "broker_submit",
                "place_order",
            } and child not in (False, None, 0, "", "false", "False"):
                raise RuntimeError(f"live/broker authority forbidden at {child_prefix}")
            reject_live_authority(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_live_authority(child, f"{prefix}[{index}]")


def run_acceptance(root: Path, request_rel: str, output_name: str):
    output = root / output_name
    proc = subprocess.run(
        [
            "python",
            ENTRYPOINT,
            "--request-json",
            request_rel,
            "--repo-root",
            ".",
            "--output-json",
            output_name,
        ],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    if not output.exists():
        raise RuntimeError(
            f"acceptance output missing for {request_rel}; exit={proc.returncode}; output_sha256="
            + hashlib.sha256(proc.stdout).hexdigest()
        )
    result = load_json(output)
    return proc.returncode, result, hashlib.sha256(proc.stdout).hexdigest()


def bool_at(payload: dict, *path: str) -> bool:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return False
        current = current.get(key)
    return current is True


def assert_terminal_contract(matched: dict, mismatch: dict) -> None:
    matched_guard = matched.get("review_guard") if isinstance(matched.get("review_guard"), dict) else {}
    matched_apply = matched.get("apply_result") if isinstance(matched.get("apply_result"), dict) else {}
    matched_safety = matched.get("safety") if isinstance(matched.get("safety"), dict) else {}
    if not (
        matched.get("ok") is True
        and matched.get("status") == "reviewed_apply_readback_pass"
        and matched.get("identity_match") is True
        and matched_guard.get("status") == "PASS"
        and matched_apply.get("config_write_applied") is True
        and matched_apply.get("canonical_writer_invoked") is True
        and matched.get("readback") is not None
        and matched_safety.get("broker_submit") is False
        and matched_safety.get("live_unlock") is False
        and matched_safety.get("runtime_owner_started") is False
    ):
        raise RuntimeError("matched reviewed-activation terminal contract failed")

    mismatch_guard = mismatch.get("review_guard") if isinstance(mismatch.get("review_guard"), dict) else {}
    mismatch_apply = mismatch.get("apply_result") if isinstance(mismatch.get("apply_result"), dict) else {}
    mismatch_safety = mismatch.get("safety") if isinstance(mismatch.get("safety"), dict) else {}
    if not (
        mismatch.get("ok") is False
        and mismatch.get("status") == "apply_blocked"
        and mismatch.get("readback") is None
        and mismatch_guard.get("status") == "FAIL_CLOSED"
        and mismatch_apply.get("config_write_applied") is not True
        and mismatch_apply.get("canonical_writer_invoked") is False
        and mismatch_safety.get("broker_submit") is False
        and mismatch_safety.get("live_unlock") is False
        and mismatch_safety.get("runtime_owner_started") is False
    ):
        raise RuntimeError("mismatched reviewed-activation fail-closed contract failed")


def consume(envelope_path: Path, private_key_path: Path, run_id: str) -> dict:
    envelope = load_json(envelope_path)
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
        raise RuntimeError("envelope key set mismatch")
    if (
        envelope.get("schema") != SCHEMA
        or str(envelope.get("run_id")) != str(run_id)
        or envelope.get("authority") != AUTHORITY
        or envelope.get("harness") != HARNESS
    ):
        raise RuntimeError("envelope contract mismatch")

    private = x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    recipient_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if envelope.get("recipient_key_id") != recipient_key_id:
        raise RuntimeError("recipient key mismatch")

    associated_data = aad(str(run_id), recipient_key_id)
    sender = x25519.X25519PublicKey.from_public_bytes(b64d(envelope["sender_public_b64"]))
    shared = private.exchange(sender)
    plaintext = ChaCha20Poly1305(derive(shared, associated_data)).decrypt(
        b64d(envelope["nonce_b64"]),
        b64d(envelope["ciphertext_b64"]),
        associated_data,
    )
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise RuntimeError("payload exceeds maximum plaintext size")
    plaintext_sha256 = hashlib.sha256(plaintext).hexdigest()
    if plaintext_sha256 != envelope.get("plaintext_sha256"):
        raise RuntimeError("payload digest mismatch")

    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as archive:
        members = archive.getmembers()
        file_members = [member for member in members if member.isfile()]
        if len(file_members) > MAX_FILES:
            raise RuntimeError("payload file count exceeds limit")
        for member in members:
            if member.issym() or member.islnk() or not safe_member_name(member.name):
                raise RuntimeError(f"unsafe payload member: {member.name}")
            if member.isfile() and member.size > MAX_MEMBER_BYTES:
                raise RuntimeError(f"payload member too large: {member.name}")

        names = {member.name for member in file_members}
        if "manifest.json" not in names:
            raise RuntimeError("manifest missing")
        manifest = json.loads(archive.extractfile("manifest.json").read().decode("utf-8"))
        if not isinstance(manifest, dict):
            raise RuntimeError("manifest root must be object")
        if (
            manifest.get("schema") != PAYLOAD_SCHEMA
            or manifest.get("harness") != HARNESS
            or manifest.get("authority") != AUTHORITY
            or manifest.get("mm_head_sha") != MM_HEAD_SHA
            or manifest.get("entrypoint") != ENTRYPOINT
            or manifest.get("matched_request") != MATCHED_REQUEST
            or manifest.get("mismatch_request") != MISMATCH_REQUEST
        ):
            raise RuntimeError("manifest contract mismatch")
        declared_hashes = manifest.get("file_sha256")
        if not isinstance(declared_hashes, dict):
            raise RuntimeError("manifest file_sha256 missing")
        expected_names = set(declared_hashes) | {"manifest.json"}
        if names != expected_names:
            raise RuntimeError("payload file set differs from manifest")
        if ENTRYPOINT not in names or MATCHED_REQUEST not in names or MISMATCH_REQUEST not in names:
            raise RuntimeError("required acceptance files missing")

        with tempfile.TemporaryDirectory(prefix="p12-terminal-acceptance-") as tempdir:
            root = Path(tempdir)
            archive.extractall(root)
            for relative, expected_hash in declared_hashes.items():
                if not safe_member_name(relative):
                    raise RuntimeError(f"unsafe declared file path: {relative}")
                actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
                if actual != str(expected_hash).lower():
                    raise RuntimeError(f"private source digest mismatch: {relative}")

            matched_request = load_json(root / MATCHED_REQUEST)
            mismatch_request = load_json(root / MISMATCH_REQUEST)
            reject_live_authority(matched_request)
            reject_live_authority(mismatch_request)

            matched_exit, matched, matched_output_sha = run_acceptance(
                root, MATCHED_REQUEST, "matched-result.json"
            )
            mismatch_exit, mismatch, mismatch_output_sha = run_acceptance(
                root, MISMATCH_REQUEST, "mismatch-result.json"
            )
            assert_terminal_contract(matched, mismatch)

    return {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "harness": HARNESS,
        "mm_head_sha": MM_HEAD_SHA,
        "payload_sha256": plaintext_sha256,
        "status": "PASS",
        "matched_exit_code": matched_exit,
        "matched_status": matched.get("status"),
        "matched_review_guard": matched.get("review_guard", {}).get("status"),
        "matched_identity_match": matched.get("identity_match") is True,
        "matched_config_write_applied": bool_at(matched, "apply_result", "config_write_applied"),
        "matched_canonical_writer_invoked": bool_at(matched, "apply_result", "canonical_writer_invoked"),
        "matched_output_sha256": matched_output_sha,
        "mismatch_exit_code": mismatch_exit,
        "mismatch_status": mismatch.get("status"),
        "mismatch_review_guard": mismatch.get("review_guard", {}).get("status"),
        "mismatch_readback_absent": mismatch.get("readback") is None,
        "mismatch_config_write_applied": bool_at(mismatch, "apply_result", "config_write_applied"),
        "mismatch_canonical_writer_invoked": bool_at(mismatch, "apply_result", "canonical_writer_invoked"),
        "mismatch_output_sha256": mismatch_output_sha,
        "broker_submit": False,
        "live_unlock": False,
        "runtime_owner_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(args.envelope, args.private_key, args.run_id)
    print("P12_TERMINAL_ACCEPTANCE_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
