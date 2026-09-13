from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "forward-inventory-ephemeral-x25519-v1"
RETURN_SCHEMA = "forward-inventory-return-x25519-v1"
PAYLOAD_SCHEMA = "foundry.forward_inventory_proof_payload.v1"
HARNESS = "forward_challenger_inventory_r1"
INFO = b"research-foundry-forward-inventory-proof-v1"
RETURN_INFO = b"research-foundry-forward-inventory-proof-return-v1"
EXPECTED_SOURCE_REF = "b5787db94241e49f79e36520c7cfbcd5600e266f"
EXPECTED_MATRIX_PATH = "model_forward/program_matrix.v1.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _key_id(raw: bytes) -> str:
    return "sha256:" + _sha(raw)


def _aad(schema: str, run_id: str, harness: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": schema,
            "run_id": str(run_id),
            "authority": "research_only",
            "harness": harness,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=info,
    ).derive(shared)


def _decrypt_input(envelope: dict, private_raw: bytes, run_id: str, harness: str) -> bytes:
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
        raise RuntimeError("input envelope field-set mismatch")
    if envelope["schema"] != SCHEMA or str(envelope["run_id"]) != str(run_id):
        raise RuntimeError("input run identity mismatch")
    if envelope["authority"] != "research_only" or envelope["harness"] != harness:
        raise RuntimeError("input authority/harness mismatch")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    expected_id = _key_id(recipient_raw)
    if envelope["recipient_key_id"] != expected_id:
        raise RuntimeError("input recipient fingerprint mismatch")
    sender_raw = _b64d(envelope["sender_public_b64"])
    nonce = _b64d(envelope["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("input key/nonce shape invalid")
    aad = _aad(SCHEMA, run_id, harness, expected_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad, INFO)).decrypt(
        nonce, _b64d(envelope["ciphertext_b64"]), aad
    )
    if _sha(plaintext) != envelope["plaintext_sha256"]:
        raise RuntimeError("input plaintext digest mismatch")
    return plaintext


def _extract_payload(payload: bytes, root: Path) -> dict:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        names = {m.name for m in members}
        expected = {"payload-manifest.json", EXPECTED_MATRIX_PATH}
        if names != expected:
            raise RuntimeError(f"payload file-set mismatch: {sorted(names ^ expected)}")
        for member in members:
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("unsafe payload path")
            src = tf.extractfile(member)
            if src is None:
                raise RuntimeError(f"unable to read {member.name}")
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read())
    manifest = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PAYLOAD_SCHEMA or manifest.get("harness") != HARNESS:
        raise RuntimeError("payload manifest identity mismatch")
    if manifest.get("source_ref") != EXPECTED_SOURCE_REF:
        raise RuntimeError("payload source ref mismatch")
    files = manifest.get("files") or {}
    if set(files) != {EXPECTED_MATRIX_PATH}:
        raise RuntimeError("payload manifest file-set mismatch")
    matrix_bytes = (root / EXPECTED_MATRIX_PATH).read_bytes()
    if _sha(matrix_bytes) != files[EXPECTED_MATRIX_PATH]:
        raise RuntimeError("matrix digest mismatch")
    return manifest


def _prove(matrix: dict) -> dict:
    if matrix.get("schema") != "foundry.forward_program_matrix.v1":
        raise RuntimeError("matrix schema mismatch")
    programs = matrix.get("programs") or []
    by = {row["program_id"]: row for row in programs}
    if len(by) != len(programs):
        raise RuntimeError("duplicate program id")

    p160 = by["P160_FIXED_P46_P47_COMBINATION"]
    if p160.get("forward_state") != "PRESTART_DESCRIPTIVE_SHADOW":
        raise RuntimeError("P160 state mismatch")
    latest_p160 = p160.get("latest_observation") or {}
    if latest_p160.get("scientific_forward_credit") is not False:
        raise RuntimeError("P160 scientific credit boundary violated")
    if latest_p160.get("first_scientific_signal_boundary") != "2026-09-30":
        raise RuntimeError("P160 signal boundary mismatch")

    currency = by["DEVELOPED_EXUS_CURRENCY_HEDGE"]
    if currency.get("forward_state") != "PROSPECTIVE_REGISTERED_AWAITING_ENTRY_SESSION":
        raise RuntimeError("currency hedge state mismatch")
    latest_currency = currency.get("latest_observation") or {}
    if latest_currency.get("entry_date") is not None:
        raise RuntimeError("currency hedge retroactive entry detected")
    if latest_currency.get("scorecard") is not None:
        raise RuntimeError("currency hedge premature scorecard detected")
    if (latest_currency.get("regime_context") or {}).get("timing_authority") is not False:
        raise RuntimeError("currency regime gained timing authority")

    boundaries = matrix.get("boundaries") or {}
    required_true = (
        "matrix_is_not_ranker",
        "matrix_is_not_allocator",
        "matrix_does_not_grant_scientific_credit",
    )
    if not all(boundaries.get(k) is True for k in required_true):
        raise RuntimeError("matrix authority boundary mismatch")
    if boundaries.get("runtime_or_broker_authority") is not False:
        raise RuntimeError("matrix gained runtime/broker authority")

    return {
        "proof_passed": True,
        "program_count": len(programs),
        "p160_state": p160["forward_state"],
        "p160_first_scientific_signal_boundary": latest_p160["first_scientific_signal_boundary"],
        "currency_state": currency["forward_state"],
        "currency_entry_date": latest_currency["entry_date"],
        "currency_regime_timing_authority": latest_currency["regime_context"]["timing_authority"],
        "matrix_is_not_ranker": boundaries["matrix_is_not_ranker"],
        "matrix_is_not_allocator": boundaries["matrix_is_not_allocator"],
        "matrix_does_not_grant_scientific_credit": boundaries["matrix_does_not_grant_scientific_credit"],
        "runtime_or_broker_authority": boundaries["runtime_or_broker_authority"],
    }


def _encrypt_return(receipt: bytes, manifest: dict, run_id: str, harness: str) -> dict:
    recipient_raw = _b64d(str(manifest["return_recipient_b64"]))
    if len(recipient_raw) != 32:
        raise RuntimeError("return recipient invalid")
    key_id = _key_id(recipient_raw)
    if manifest.get("return_recipient_key_id") != key_id:
        raise RuntimeError("return recipient fingerprint mismatch")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    aad = _aad(RETURN_SCHEMA, run_id, harness, key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(_derive(shared, aad, RETURN_INFO)).encrypt(
        nonce, receipt, aad
    )
    return {
        "schema": RETURN_SCHEMA,
        "run_id": str(run_id),
        "authority": "research_only",
        "harness": harness,
        "recipient_key_id": key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_sha256": _sha(receipt),
    }


def consume(envelope_path: Path, private_key_path: Path, run_id: str, output: Path) -> dict:
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("recipient private key invalid")
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    plaintext = _decrypt_input(envelope, private_raw, run_id, HARNESS)
    with tempfile.TemporaryDirectory(prefix="forward-inventory-proof-") as td:
        root = Path(td)
        manifest = _extract_payload(plaintext, root)
        matrix_bytes = (root / EXPECTED_MATRIX_PATH).read_bytes()
        proof = _prove(json.loads(matrix_bytes.decode("utf-8")))
        receipt = {
            "schema": "forward-inventory-public-compute-receipt-v1",
            "authority": "research_only",
            "harness": HARNESS,
            "source_ref": EXPECTED_SOURCE_REF,
            "matrix_sha256": _sha(matrix_bytes),
            **proof,
            "private_source_persisted": False,
            "private_stdout_exposed": False,
            "private_stderr_exposed": False,
        }
        receipt_bytes = (json.dumps(receipt, sort_keys=True) + "\n").encode("utf-8")
        output.write_text(
            json.dumps(_encrypt_return(receipt_bytes, manifest, run_id, HARNESS), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt


def self_test() -> None:
    matrix = {
        "schema": "foundry.forward_program_matrix.v1",
        "programs": [
            {
                "program_id": "P160_FIXED_P46_P47_COMBINATION",
                "forward_state": "PRESTART_DESCRIPTIVE_SHADOW",
                "latest_observation": {
                    "scientific_forward_credit": False,
                    "first_scientific_signal_boundary": "2026-09-30",
                },
            },
            {
                "program_id": "DEVELOPED_EXUS_CURRENCY_HEDGE",
                "forward_state": "PROSPECTIVE_REGISTERED_AWAITING_ENTRY_SESSION",
                "latest_observation": {
                    "entry_date": None,
                    "scorecard": None,
                    "regime_context": {"timing_authority": False},
                },
            },
        ],
        "boundaries": {
            "matrix_is_not_ranker": True,
            "matrix_is_not_allocator": True,
            "matrix_does_not_grant_scientific_credit": True,
            "runtime_or_broker_authority": False,
        },
    }
    receipt = _prove(matrix)
    assert receipt["proof_passed"] is True
    assert receipt["program_count"] == 2
    print("FORWARD_INVENTORY_EPHEMERAL_PROOF_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope")
    p.add_argument("--private-key")
    p.add_argument("--run-id")
    p.add_argument("--return-envelope")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.envelope, args.private_key, args.run_id, args.return_envelope)):
        p.error("envelope, private-key, run-id and return-envelope are required")
    receipt = consume(
        Path(args.envelope),
        Path(args.private_key),
        str(args.run_id),
        Path(args.return_envelope),
    )
    print(
        "FORWARD_INVENTORY_PUBLIC_PROOF=PASS "
        f"programs={receipt['program_count']} matrix_sha256={receipt['matrix_sha256']}"
    )


if __name__ == "__main__":
    main()
