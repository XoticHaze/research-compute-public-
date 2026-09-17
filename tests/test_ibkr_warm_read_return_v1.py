from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import ibkr_warm_read_return_v1 as mod


class WarmReadReturnTests(unittest.TestCase):
    def _recipient(self):
        private = x25519.X25519PrivateKey.generate()
        public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return private, base64.b64encode(public_raw).decode("ascii"), "sha256:" + hashlib.sha256(public_raw).hexdigest()

    def _snapshot(self):
        return {
            "schema": mod.SNAPSHOT_SCHEMA,
            "generated_at": "2026-09-17T00:00:00+00:00",
            "run_id": "12345",
            "public_head": "a" * 40,
            "authority": mod.AUTHORITY,
            "harness": mod.HARNESS,
            "trading_mode": "paper",
            "read_only": True,
            "managed_accounts": ["DU123456"],
            "account_summary": [
                {"account": "DU123456", "tag": "NetLiquidation", "value": "100000", "currency": "USD", "model_code": ""}
            ],
            "positions": [
                {
                    "account": "DU123456",
                    "contract": {"conId": 266093, "symbol": "AMAT", "secType": "STK"},
                    "position": 2.0,
                    "avg_cost": 150.0,
                }
            ],
            "open_trades": [],
            "broker_time": "2026-09-17T00:00:00+00:00",
            "post_auth_handoff": {"schema": "mmibkr-ibkr-post-auth-handoff-v2"},
            "forward_bars": [{"symbol": "AMAT", "close": 151.0}],
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "historical_market_data": True,
                "order_submission": False,
                "global_cancel": False,
                "live_execution": False,
            },
        }

    def test_encrypt_snapshot_round_trip_is_run_and_recipient_bound(self):
        private, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            envelope = mod.encrypt_snapshot(
                snapshot=snapshot,
                recipient_b64=recipient_b64,
                recipient_key_id=recipient_key_id,
                run_id="12345",
                output_dir=root,
            )
            self.assertEqual(envelope["schema"], mod.RETURN_ENVELOPE_SCHEMA)
            self.assertEqual(envelope["run_id"], "12345")
            self.assertEqual(envelope["recipient_key_id"], recipient_key_id)
            self.assertGreater(len(envelope["chunks"]), 0)

            pieces = []
            for node in envelope["chunks"]:
                raw = (root / node["local_name"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), node["sha256"])
                self.assertEqual(len(raw), node["chars"])
                self.assertTrue(node["path"].startswith("rendezvous/returns/12345/"))
                pieces.append(raw.decode("ascii"))
            ciphertext = base64.b64decode("".join(pieces).encode("ascii"), validate=True)
            self.assertEqual(hashlib.sha256(ciphertext).hexdigest(), envelope["ciphertext_sha256"])

            sender_raw = base64.b64decode(envelope["sender_public_b64"].encode("ascii"), validate=True)
            nonce = base64.b64decode(envelope["nonce_b64"].encode("ascii"), validate=True)
            aad = mod._aad(run_id="12345", recipient_key_id=recipient_key_id)
            shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=hashlib.sha256(aad).digest(),
                info=mod.RETURN_INFO,
            ).derive(shared)
            plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
            self.assertEqual(hashlib.sha256(plaintext).hexdigest(), envelope["plaintext_sha256"])
            self.assertEqual(json.loads(plaintext.decode("utf-8")), snapshot)

    def test_wrong_recipient_fingerprint_fails_closed(self):
        _, recipient_b64, _ = self._recipient()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                mod.encrypt_snapshot(
                    snapshot=self._snapshot(),
                    recipient_b64=recipient_b64,
                    recipient_key_id="sha256:" + "0" * 64,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_identity_and_mutation_boundaries_fail_closed(self):
        _, recipient_b64, recipient_key_id = self._recipient()
        bad_run = self._snapshot()
        bad_run["run_id"] = "999"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
                mod.encrypt_snapshot(
                    snapshot=bad_run,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

        mutable = self._snapshot()
        mutable["capabilities"]["order_submission"] = True
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "mutation boundary"):
                mod.encrypt_snapshot(
                    snapshot=mutable,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_source_has_readonly_connect_and_no_mutation_calls(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertIn("readonly=True", source)
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertNotIn("qualifyContracts(", source)
        self.assertIn('"order_submission": False', source)
        self.assertIn('"global_cancel": False', source)
        self.assertIn('"live_execution": False', source)


if __name__ == "__main__":
    unittest.main()
