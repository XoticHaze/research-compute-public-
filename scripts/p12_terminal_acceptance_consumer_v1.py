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
MM_HEAD_SHA = "d98ecf34d5ae5209251f1cd7e3a996f18659d04f"
INFO = b"commandcenter-p12-terminal-acceptance-r4"
ENTRYPOINT = "scripts/operator/p12_reviewed_activation_http_browser_acceptance.py"
BUNDLE = "acceptance/reviewed-activation-bundle.json"
MAX_FILES = 160
MAX_PLAINTEXT_BYTES = 20 * 1024 * 1024
MAX_MEMBER_BYTES = 6 * 1024 * 1024


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def aad(run_id: str, key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


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


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return value


def reject_live_authority(value, prefix: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in {
                "enable_live_trading",
                "live_trading_enabled",
                "live_enabled",
                "live_unlock",
                "broker_submit",
                "place_order",
            } and child not in (False, None, 0, "", "false", "False"):
                raise RuntimeError(f"live/broker authority forbidden at {prefix}.{key}")
            reject_live_authority(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_live_authority(child, f"{prefix}[{index}]")


def run_acceptance(root: Path) -> tuple[int, dict, str]:
    output = root / "p12-product-result.json"
    proc = subprocess.run(
        [
            "python",
            ENTRYPOINT,
            "--bundle-json",
            BUNDLE,
            "--output-json",
            str(output.name),
        ],
        cwd=root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "ENABLE_LIVE_TRADING": "0",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
    )
    if not output.exists():
        raise RuntimeError(
            f"product acceptance output missing; exit={proc.returncode}; output_sha256="
            f"{hashlib.sha256(proc.stdout).hexdigest()}"
        )
    return proc.returncode, load_json(output), hashlib.sha256(proc.stdout).hexdigest()


def identity_matches(proposed: dict, readback: dict) -> bool:
    required = ("symbol", "signal_symbol", "timeframe", "strategy_id", "parameter_preset_id")
    for key in required:
        proposed_value = str(proposed.get(key) or "").strip()
        readback_value = str(readback.get(key) or "").strip()
        if key == "symbol":
            proposed_value = proposed_value.upper()
            readback_value = readback_value.upper()
        if proposed_value and proposed_value != readback_value:
            return False
    proposed_runtime_id = str(proposed.get("runtime_id") or "").strip()
    readback_runtime_id = str(readback.get("runtime_id") or "").strip()
    if proposed_runtime_id and proposed_runtime_id != readback_runtime_id:
        return False
    return True


def assert_terminal_contract(result: dict) -> None:
    browser = result.get("browser_backend_acceptance") if isinstance(result.get("browser_backend_acceptance"), dict) else {}
    matched = browser.get("matched") if isinstance(browser.get("matched"), dict) else {}
    mismatch = browser.get("mismatch") if isinstance(browser.get("mismatch"), dict) else {}
    apply_payload = ((matched.get("apply") or {}).get("payload") or {}) if isinstance(matched.get("apply"), dict) else {}
    readback_payload = ((matched.get("readback") or {}).get("payload") or {}) if isinstance(matched.get("readback"), dict) else {}
    blocked_payload = ((mismatch.get("blocked") or {}).get("payload") or {}) if isinstance(mismatch.get("blocked"), dict) else {}
    safety = result.get("safety") if isinstance(result.get("safety"), dict) else {}
    proposed_identity = matched.get("proposed_identity") if isinstance(matched.get("proposed_identity"), dict) else {}
    readback_identity = matched.get("readback_identity") if isinstance(matched.get("readback_identity"), dict) else {}
    if not (
        result.get("ok") is True
        and result.get("status") == "PASS"
        and browser.get("ok") is True
        and apply_payload.get("review_guard", {}).get("status") == "PASS"
        and apply_payload.get("config_write_applied") is True
        and apply_payload.get("canonical_writer_invoked") is True
        and readback_payload.get("ok") is True
        and matched.get("identity_match") is True
        and bool(proposed_identity)
        and bool(readback_identity)
        and identity_matches(proposed_identity, readback_identity)
        and blocked_payload.get("review_guard", {}).get("status") == "FAIL_CLOSED"
        and blocked_payload.get("config_write_applied") is False
        and blocked_payload.get("canonical_writer_invoked") is False
        and mismatch.get("readback_suppressed") is True
        and safety.get("live_trading_forced_off") is True
        and safety.get("broker_submit") is False
        and safety.get("runtime_owner_started") is False
        and safety.get("canonical_writer_unchanged") is True
    ):
        raise RuntimeError("P12 product-level exact-readback terminal contract failed")


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
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if envelope.get("recipient_key_id") != key_id:
        raise RuntimeError("recipient key mismatch")
    associated_data = aad(str(run_id), key_id)
    sender = x25519.X25519PublicKey.from_public_bytes(b64d(envelope["sender_public_b64"]))
    plaintext = ChaCha20Poly1305(derive(private.exchange(sender), associated_data)).decrypt(
        b64d(envelope["nonce_b64"]),
        b64d(envelope["ciphertext_b64"]),
        associated_data,
    )
    if len(plaintext) > MAX_PLAINTEXT_BYTES or hashlib.sha256(plaintext).hexdigest() != envelope.get("plaintext_sha256"):
        raise RuntimeError("payload size/digest mismatch")
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as archive:
        members = archive.getmembers()
        files = [member for member in members if member.isfile()]
        if len(files) > MAX_FILES:
            raise RuntimeError("payload file count exceeds limit")
        for member in members:
            if member.issym() or member.islnk() or not safe_member_name(member.name) or (
                member.isfile() and member.size > MAX_MEMBER_BYTES
            ):
                raise RuntimeError(f"unsafe payload member: {member.name}")
        names = {member.name for member in files}
        if "manifest.json" not in names:
            raise RuntimeError("manifest missing")
        manifest = json.loads(archive.extractfile("manifest.json").read().decode("utf-8"))
        if (
            manifest.get("schema") != PAYLOAD_SCHEMA
            or manifest.get("harness") != HARNESS
            or manifest.get("authority") != AUTHORITY
            or manifest.get("mm_head_sha") != MM_HEAD_SHA
            or manifest.get("entrypoint") != ENTRYPOINT
            or manifest.get("bundle") != BUNDLE
        ):
            raise RuntimeError("manifest contract mismatch")
        declared = manifest.get("file_sha256")
        if not isinstance(declared, dict) or names != set(declared) | {"manifest.json"} or ENTRYPOINT not in names or BUNDLE not in names:
            raise RuntimeError("payload file-set mismatch")
        with tempfile.TemporaryDirectory(prefix="p12-terminal-") as tempdir:
            root = Path(tempdir)
            archive.extractall(root)
            for relative, expected in declared.items():
                if not safe_member_name(relative) or hashlib.sha256((root / relative).read_bytes()).hexdigest() != str(expected).lower():
                    raise RuntimeError(f"private source digest mismatch: {relative}")
            reject_live_authority(load_json(root / BUNDLE))
            exit_code, result, output_sha = run_acceptance(root)
            assert_terminal_contract(result)
    return {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "harness": HARNESS,
        "mm_head_sha": MM_HEAD_SHA,
        "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
        "status": "PASS",
        "product_acceptance_exit_code": exit_code,
        "product_acceptance_output_sha256": output_sha,
        "review_guard": "PASS",
        "config_write_applied": True,
        "canonical_writer_invoked": True,
        "exact_identity_match": True,
        "deliberate_mismatch_fail_closed": True,
        "mismatch_canonical_writer_invoked": False,
        "mismatch_readback_suppressed": True,
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
