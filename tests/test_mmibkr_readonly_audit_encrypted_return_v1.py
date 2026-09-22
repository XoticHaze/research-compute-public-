from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mmibkr_readonly_audit_encrypted_return_v1.py"
spec = importlib.util.spec_from_file_location("enc", MODULE_PATH)
enc = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(enc)


class ReadonlyAuditEncryptedReturnTests(unittest.TestCase):
    def _request(self):
        private = x25519.X25519PrivateKey.generate()
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        request = {
            "return_schema": enc.REQUEST_SCHEMA,
            "request_id": "audit_20260922_test",
            "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
            "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
        }
        return private, request

    def _audit(self):
        return {
            "schema": enc.AUDIT_SCHEMA,
            "ok": True,
            "rows": [{"runtime_id": "x", "crw": {"crw_score": -3.1}}],
            "safety": {
                "read_only": True,
                "broker_action": False,
                "broker_request_made": False,
                "paper_submit_invoked": False,
                "cancel_invoked": False,
                "flatten_invoked": False,
                "strategy_spec_mutation": False,
                "runtime_authority_mutation": False,
                "account_positions_promoted_to_bot_inventory": False,
                "live_execution_allowed": False,
            },
        }

    def test_encrypt_roundtrip(self):
        private, request = self._request()
        audit = self._audit()
        envelope = enc.encrypt_audit(audit, request)
        sender_public = base64.b64decode(envelope["sender_public_b64"])
        nonce = base64.b64decode(envelope["nonce_b64"])
        ciphertext = base64.b64decode(envelope["ciphertext_b64"])
        aad = enc._aad(
            request_id=envelope["request_id"],
            recipient_key_id=envelope["recipient_key_id"],
        )
        shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_public))
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=hashlib.sha256(aad).digest(),
            info=enc.INFO,
        ).derive(shared)
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
        self.assertEqual(json.loads(plaintext), audit)

    def test_rejects_live_enabled_payload(self):
        _, request = self._request()
        audit = self._audit()
        audit["safety"]["live_execution_allowed"] = True
        with self.assertRaisesRegex(RuntimeError, "live_execution_allowed"):
            enc.encrypt_audit(audit, request)


if __name__ == "__main__":
    unittest.main()
