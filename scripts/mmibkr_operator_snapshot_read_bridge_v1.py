from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


REQUEST_SCHEMA = "mmibkr.operator_snapshot_read_bridge_request.v1"
MACHINE_READ_SCHEMA = "mmibkr.operator_console_machine_read.v1"
SNAPSHOT_SCHEMA = "mmibkr.cloud_operator_snapshot.v1"
PAYLOAD_SCHEMA = "mmibkr.operator_snapshot_encrypted_payload.v1"
ENVELOPE_SCHEMA = "mmibkr.operator_snapshot_encrypted_return_x25519.v1"
INFO = b"mmibkr-operator-snapshot-read-bridge-v1"
CHUNK_CHARS = 8000
EXPECTED_REPOSITORY = "XoticHaze/research-compute-public-"
EXPECTED_WORKFLOW_REF = (
    "XoticHaze/research-compute-public-/.github/workflows/"
    "mmibkr-operator-snapshot-read-bridge-r1.yml@refs/heads/main"
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: str | Path) -> dict[str, Any]:
    node = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("JSON object required")
    return node


def validate_request(node: Mapping[str, Any]) -> tuple[str, bytes, str]:
    if node.get("schema") != REQUEST_SCHEMA:
        raise RuntimeError("operator bridge request schema rejected")
    request_id = str(node.get("request_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,96}", request_id):
        raise RuntimeError("operator bridge request id rejected")
    recipient_b64 = str(node.get("recipient_b64") or "").strip()
    recipient_key_id = str(node.get("recipient_key_id") or "").strip()
    try:
        recipient_raw = base64.b64decode(recipient_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("operator bridge recipient key is not valid base64") from exc
    if len(recipient_raw) != 32:
        raise RuntimeError("operator bridge recipient key must be 32-byte X25519")
    expected_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if recipient_key_id != expected_key_id:
        raise RuntimeError("operator bridge recipient fingerprint mismatch")
    return request_id, recipient_raw, recipient_key_id


def validate_machine_read(node: Mapping[str, Any]) -> dict[str, Any]:
    if node.get("ok") is not True or node.get("schema") != MACHINE_READ_SCHEMA:
        raise RuntimeError("operator machine read rejected")
    if node.get("broker_mutation_authority") is not False:
        raise RuntimeError("operator machine read carries broker authority")
    if node.get("live_execution_allowed") is not False:
        raise RuntimeError("operator machine read permits live execution")

    reader = node.get("reader") if isinstance(node.get("reader"), Mapping) else {}
    if reader.get("repository") != EXPECTED_REPOSITORY:
        raise RuntimeError("operator machine reader repository mismatch")
    if reader.get("repository_visibility") != "public":
        raise RuntimeError("operator machine reader visibility mismatch")
    if reader.get("workflow_ref") != EXPECTED_WORKFLOW_REF:
        raise RuntimeError("operator machine reader workflow mismatch")

    snapshot = node.get("snapshot")
    if not isinstance(snapshot, Mapping) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise RuntimeError("operator snapshot schema rejected")
    if snapshot.get("mode") != "paper" or snapshot.get("live_enabled") is not False:
        raise RuntimeError("operator snapshot must remain paper-only")

    privacy = snapshot.get("privacy") if isinstance(snapshot.get("privacy"), Mapping) else {}
    authority = snapshot.get("authority") if isinstance(snapshot.get("authority"), Mapping) else {}
    required_privacy = {
        "private_operator_state": True,
        "account_identifiers_included": False,
        "credentials_included": False,
        "tokens_included": False,
        "private_source_included": False,
        "execution_authority_included": False,
    }
    for key, expected in required_privacy.items():
        if privacy.get(key) is not expected:
            raise RuntimeError(f"operator snapshot privacy contract rejected:{key}")

    required_authority = {
        "presentation_projection_only": True,
        "strategy_authority": False,
        "execution_policy_authority": False,
        "sizing_authority": False,
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }
    for key, expected in required_authority.items():
        if authority.get(key) is not expected:
            raise RuntimeError(f"operator snapshot authority contract rejected:{key}")
    return dict(snapshot)


def _aad(*, request_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": ENVELOPE_SCHEMA,
            "request_id": request_id,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encrypt_machine_read(
    machine_read: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    request_id, recipient_raw, recipient_key_id = validate_request(request)
    snapshot = validate_machine_read(machine_read)
    reader = machine_read.get("reader") if isinstance(machine_read.get("reader"), Mapping) else {}

    payload = {
        "schema": PAYLOAD_SCHEMA,
        "request_id": request_id,
        "generated_at_utc": _iso_now(),
        "cloudflare_stored_at_utc": machine_read.get("stored_at_utc"),
        "source": {
            "reader_repository": reader.get("repository"),
            "reader_workflow_ref": reader.get("workflow_ref"),
            "reader_run_id": reader.get("run_id"),
        },
        "snapshot": snapshot,
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }
    plaintext = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = _aad(request_id=request_id, recipient_key_id=recipient_key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    encoded = base64.b64encode(ciphertext).decode("ascii")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    response_root = f"rendezvous/returns/mmibkr-operator-snapshot/{request_id}"
    manifest: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(encoded), CHUNK_CHARS)):
        chunk = encoded[start : start + CHUNK_CHARS]
        local_name = f"operator-snapshot-{index:03d}.txt"
        path = f"{response_root}/{local_name}"
        raw = chunk.encode("ascii")
        (out / local_name).write_bytes(raw)
        manifest.append(
            {
                "path": path,
                "local_name": local_name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "chars": len(raw),
            }
        )

    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "request_id": request_id,
        "generated_at_utc": _iso_now(),
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": manifest,
        "plaintext_published": False,
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }
    (out / "operator-snapshot-envelope.json").write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine-read", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    envelope = encrypt_machine_read(
        _load(args.machine_read),
        _load(args.request),
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "schema": "mmibkr.operator_snapshot_read_bridge_receipt.v1",
                "request_id": envelope["request_id"],
                "recipient_key_id": envelope["recipient_key_id"],
                "ciphertext_sha256": envelope["ciphertext_sha256"],
                "chunk_count": len(envelope["chunks"]),
                "plaintext_published": False,
                "broker_mutation_authority": False,
                "live_execution_allowed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
