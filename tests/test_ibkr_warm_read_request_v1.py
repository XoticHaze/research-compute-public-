from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import ephemeral_x25519_chunked_v1 as crypto
from scripts import ibkr_warm_read_request_v1 as mod


class WarmReadRequestTests(unittest.TestCase):
    def _return_recipient(self):
        private = x25519.X25519PrivateKey.generate()
        raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return {
            "schema": mod.RETURN_RECIPIENT_SCHEMA,
            "recipient_b64": base64.b64encode(raw).decode("ascii"),
            "recipient_key_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
        }

    def _request(self):
        return {
            "schema": mod.REQUEST_SCHEMA,
            "run_id": "12345",
            "public_head": "a" * 40,
            "dispatch_nonce": "0123456789abcdef",
            "mode": "readonly",
            "symbols": ["amat", "APH", "AMAT"],
            "return_recipient": self._return_recipient(),
        }

    def test_validate_request_normalizes_symbols_and_binds_identity(self):
        node = mod.validate_request(
            self._request(),
            run_id="12345",
            public_head="a" * 40,
            dispatch_nonce="0123456789abcdef",
        )
        self.assertEqual(node["symbols"], ["AMAT", "APH"])
        self.assertEqual(node["mode"], "readonly")

    def test_validate_request_rejects_wrong_head_nonce_mode_and_recipient(self):
        cases = []
        wrong_head = self._request(); wrong_head["public_head"] = "b" * 40; cases.append((wrong_head, "public head"))
        wrong_nonce = self._request(); wrong_nonce["dispatch_nonce"] = "fedcba9876543210"; cases.append((wrong_nonce, "dispatch nonce"))
        wrong_mode = self._request(); wrong_mode["mode"] = "paper_submit_proof"; cases.append((wrong_mode, "readonly"))
        wrong_recipient = self._request(); wrong_recipient["return_recipient"]["recipient_key_id"] = "sha256:" + "0" * 64; cases.append((wrong_recipient, "fingerprint"))
        for node, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    mod.validate_request(
                        node,
                        run_id="12345",
                        public_head="a" * 40,
                        dispatch_nonce="0123456789abcdef",
                    )

    def test_materialize_decrypts_generic_transport_without_publishing_plaintext(self):
        run_id = "12345"
        request = self._request()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private_path = root / "private.b64"
            recipient = mod.generate_recipient(run_id=run_id, private_key_path=private_path)
            recipient_raw = base64.b64decode(recipient["recipient_b64"].encode("ascii"), validate=True)
            plaintext = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
            sender = x25519.X25519PrivateKey.generate()
            sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            aad = crypto.aad_bytes(
                schema=mod.ENVELOPE_SCHEMA,
                run_id=run_id,
                harness=mod.HARNESS,
                recipient_key_id=recipient["recipient_key_id"],
                authority=mod.AUTHORITY,
            )
            shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
            key = crypto.derive_key(shared, aad)
            nonce = b"\x02" * 12
            ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
            payload_b64 = base64.b64encode(ciphertext).decode("ascii")
            _, chunks = crypto.build_text_chunk_manifest(
                payload_b64,
                response_root=f"{mod.RESPONSE_ROOT}/{run_id}",
                stem="ibkr-warm-read-request",
            )
            envelope = {
                "schema": mod.ENVELOPE_SCHEMA,
                "run_id": run_id,
                "authority": mod.AUTHORITY,
                "harness": mod.HARNESS,
                "recipient_key_id": recipient["recipient_key_id"],
                "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
                "nonce_b64": base64.b64encode(nonce).decode("ascii"),
                "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
                "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
                "chunks": chunks,
            }
            output = root / "request.json"
            node = mod.materialize_request(
                envelope=envelope,
                ciphertext=ciphertext,
                private_key_path=private_path,
                run_id=run_id,
                public_head="a" * 40,
                dispatch_nonce="0123456789abcdef",
                output_path=output,
            )
            self.assertEqual(node["symbols"], ["AMAT", "APH"])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["symbols"], ["AMAT", "APH"])
            self.assertEqual(os.stat(private_path).st_mode & 0o777, 0o600)

    def test_recipient_publish_is_run_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            recipient = mod.generate_recipient(run_id="12345", private_key_path=Path(td) / "k")
            calls = []
            path = mod.publish_recipient(
                token="token",
                repository="owner/repo",
                branch="rendezvous-exchange",
                run_id="12345",
                recipient=recipient,
                publisher=lambda **kwargs: calls.append(kwargs),
            )
        self.assertEqual(path, "rendezvous/recipients/12345-ibkr-warm-read.json")
        self.assertEqual(calls[0]["path"], path)
        self.assertNotIn("AMAT", calls[0]["content"])

    def test_source_has_no_broker_mutation_or_symbol_workflow_input_dependency(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from ib_insync", source)
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertIn("mmibkr.ibkr_warm_read_request.v1", source)
        self.assertIn("plaintext_published", source)


if __name__ == "__main__":
    unittest.main()
