from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import hfdl_api_key_envelope_consumer_v1 as mod


def _envelope_factory(secret: bytes):
    def request_factory(
        authority_base,
        *,
        run_id,
        recipient_b64,
        recipient_key_id,
    ):
        recipient_raw = base64.b64decode(recipient_b64)
        assert recipient_key_id == "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
        recipient = x25519.X25519PublicKey.from_public_bytes(recipient_raw)
        ephemeral = x25519.X25519PrivateKey.generate()
        ephemeral_public = ephemeral.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        shared = ephemeral.exchange(recipient)
        salt = b"s" * 32
        iv = b"i" * 12
        aad = (
            f"mmibkr-fleet-authority|{mod.AUTHORITY}|{run_id}|{recipient_key_id}"
        ).encode()
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=aad,
        ).derive(shared)
        cipher = AESGCM(key).encrypt(iv, secret, aad)
        return {
            "schema": mod.ENVELOPE_SCHEMA,
            "authority": mod.AUTHORITY,
            "run_id": run_id,
            "recipient_key_id": recipient_key_id,
            "ephemeral_public_b64": base64.b64encode(ephemeral_public).decode(),
            "salt_b64": base64.b64encode(salt).decode(),
            "iv_b64": base64.b64encode(iv).decode(),
            "aad_b64": base64.b64encode(aad).decode(),
            "ciphertext_b64": base64.b64encode(cipher).decode(),
        }

    return request_factory


def test_consumer_writes_secret_without_emitting_it(tmp_path):
    secret = b"hfdl-secret-fixture"
    output = tmp_path / "hfdl.key"
    receipt = tmp_path / "receipt.json"

    proof = mod.consume(
        "https://fleet.example",
        run_id="12345",
        output=output,
        receipt=receipt,
        request_factory=_envelope_factory(secret),
    )

    assert proof["ok"] is True
    assert proof["plaintext_emitted"] is False
    assert proof["broker_credentials_used"] is False
    assert output.read_bytes() == secret
    assert oct(output.stat().st_mode & 0o777) == "0o600"
    persisted = json.loads(receipt.read_text())
    assert "hfdl-secret-fixture" not in receipt.read_text()
    assert persisted["classification"] == "PRIVATE_INPUT_READY"


def test_consumer_classifies_unconfigured_authority(tmp_path):
    def unavailable(*args, **kwargs):
        raise mod.AuthorityUnavailable("hfdl_authority_not_configured")

    receipt = tmp_path / "receipt.json"
    proof = mod.consume(
        "https://fleet.example",
        run_id="12345",
        output=tmp_path / "missing.key",
        receipt=receipt,
        request_factory=unavailable,
    )

    assert proof["ok"] is False
    assert proof["classification"] == "PRIVATE_INPUT_FULFILLMENT_FAILURE"
    assert proof["reason"] == "hfdl_authority_not_configured"
    assert not (tmp_path / "missing.key").exists()
