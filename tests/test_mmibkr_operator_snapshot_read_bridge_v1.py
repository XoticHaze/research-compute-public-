from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts.mmibkr_operator_snapshot_read_bridge_v1 import (
    ENVELOPE_SCHEMA,
    INFO,
    PAYLOAD_SCHEMA,
    encrypt_machine_read,
)


def _request():
    private = x25519.X25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return private, {
        "schema": "mmibkr.operator_snapshot_read_bridge_request.v1",
        "request_id": "proof_request_20260921",
        "recipient_b64": base64.b64encode(public).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public).hexdigest(),
    }


def _machine_read():
    return {
        "ok": True,
        "schema": "mmibkr.operator_console_machine_read.v1",
        "stored_at_utc": "2026-09-21T22:24:00Z",
        "reader": {
            "repository": "XoticHaze/research-compute-public-",
            "repository_visibility": "public",
            "workflow_ref": (
                "XoticHaze/research-compute-public-/.github/workflows/"
                "mmibkr-operator-snapshot-read-bridge-r1.yml@refs/heads/main"
            ),
            "run_id": "35600000000",
        },
        "snapshot": {
            "schema": "mmibkr.cloud_operator_snapshot.v1",
            "mode": "paper",
            "live_enabled": False,
            "runtime": {"source_sha": "a" * 40},
            "account": {"equity": 100000.0},
            "positions": [{"contract": {"symbol": "AMAT"}, "position": 1.0}],
            "fills": [],
            "runtimes": [{"runtime_id": "crw_amat_15m_selected", "symbol": "AMAT"}],
            "privacy": {
                "private_operator_state": True,
                "account_identifiers_included": False,
                "credentials_included": False,
                "tokens_included": False,
                "private_source_included": False,
                "execution_authority_included": False,
            },
            "authority": {
                "presentation_projection_only": True,
                "strategy_authority": False,
                "execution_policy_authority": False,
                "sizing_authority": False,
                "broker_mutation_authority": False,
                "live_execution_allowed": False,
            },
        },
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }


class OperatorSnapshotReadBridgeTests(unittest.TestCase):
    def test_round_trip_encrypts_exact_sanitized_snapshot(self):
        private, request = _request()
        machine = _machine_read()
        with tempfile.TemporaryDirectory() as td:
            envelope = encrypt_machine_read(machine, request, output_dir=td)
            self.assertEqual(envelope["schema"], ENVELOPE_SCHEMA)
            self.assertFalse(envelope["plaintext_published"])
            chunks = []
            for node in envelope["chunks"]:
                raw = (Path(td) / node["local_name"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), node["sha256"])
                chunks.append(raw.decode("ascii"))
            ciphertext = base64.b64decode("".join(chunks).encode("ascii"), validate=True)
            self.assertEqual(hashlib.sha256(ciphertext).hexdigest(), envelope["ciphertext_sha256"])

            sender_public = base64.b64decode(envelope["sender_public_b64"], validate=True)
            nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
            aad = json.dumps(
                {
                    "schema": ENVELOPE_SCHEMA,
                    "request_id": request["request_id"],
                    "recipient_key_id": request["recipient_key_id"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_public))
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=hashlib.sha256(aad).digest(),
                info=INFO,
            ).derive(shared)
            plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
            self.assertEqual(hashlib.sha256(plaintext).hexdigest(), envelope["plaintext_sha256"])
            payload = json.loads(plaintext.decode("utf-8"))
            self.assertEqual(payload["schema"], PAYLOAD_SCHEMA)
            self.assertEqual(payload["request_id"], request["request_id"])
            self.assertEqual(payload["snapshot"], machine["snapshot"])
            self.assertFalse(payload["broker_mutation_authority"])
            self.assertFalse(payload["live_execution_allowed"])

    def test_rejects_account_identifier_flag(self):
        _, request = _request()
        machine = _machine_read()
        machine["snapshot"]["privacy"]["account_identifiers_included"] = True
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "account_identifiers_included"):
                encrypt_machine_read(machine, request, output_dir=td)

    def test_rejects_wrong_reader_workflow(self):
        _, request = _request()
        machine = _machine_read()
        machine["reader"]["workflow_ref"] = "wrong"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "reader workflow mismatch"):
                encrypt_machine_read(machine, request, output_dir=td)


if __name__ == "__main__":
    unittest.main()
