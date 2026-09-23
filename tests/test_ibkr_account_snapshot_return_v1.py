import base64
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from scripts import ibkr_account_snapshot_return_v1 as mod


class AccountSnapshotReturnTests(unittest.TestCase):
    def snapshot(self):
        return {
            "schema": mod.SNAPSHOT_SCHEMA,
            "generated_at_utc": "2026-09-23T20:30:00Z",
            "run_id": "12345",
            "public_head": "a" * 40,
            "authority": mod.AUTHORITY,
            "harness": mod.HARNESS,
            "trading_mode": "paper",
            "read_only": True,
            "paper_account_verified": True,
            "managed_account_count": 1,
            "account_identifiers_included": False,
            "account_summary": [{"tag": "NetLiquidation", "value": "100000", "currency": "USD"}],
            "positions": [
                {
                    "contract": {"conId": 1, "symbol": "AMAT", "secType": "STK"},
                    "position": 325.0,
                    "avg_cost": 150.0,
                }
            ],
            "position_count": 1,
            "open_order_count": 0,
            "broker_time_utc": "2026-09-23T20:30:00Z",
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "historical_market_data": False,
                "quotes": False,
                "completed_executions": False,
                "order_submission": False,
                "order_cancel": False,
                "global_cancel": False,
                "live_execution": False,
            },
        }

    def test_account_only_contract_accepts_no_mutation_capabilities(self):
        mod.validate_snapshot(self.snapshot(), run_id="12345")

    def test_account_identifiers_are_fail_closed(self):
        node = self.snapshot()
        node["account_identifiers_included"] = True
        with self.assertRaisesRegex(RuntimeError, "account identifiers"):
            mod.validate_snapshot(node, run_id="12345")

    def test_historical_or_execution_capability_is_rejected(self):
        for key in ("historical_market_data", "order_submission", "live_execution"):
            with self.subTest(key=key):
                node = self.snapshot()
                node["capabilities"][key] = True
                with self.assertRaisesRegex(RuntimeError, "forbidden capability"):
                    mod.validate_snapshot(node, run_id="12345")

    def test_encrypted_return_is_bound_to_one_recipient(self):
        recipient_private = x25519.X25519PrivateKey.generate()
        recipient_public = recipient_private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        recipient_b64 = base64.b64encode(recipient_public).decode("ascii")
        import hashlib
        key_id = "sha256:" + hashlib.sha256(recipient_public).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            envelope = mod.encrypt_snapshot(
                snapshot=self.snapshot(),
                recipient_b64=recipient_b64,
                recipient_key_id=key_id,
                run_id="12345",
                output_dir=Path(tmp),
            )
            self.assertEqual(envelope["schema"], mod.ENVELOPE_SCHEMA)
            self.assertEqual(envelope["recipient_key_id"], key_id)
            self.assertGreaterEqual(len(envelope["chunks"]), 1)
            self.assertTrue((Path(tmp) / "ibkr-account-snapshot-envelope.json").is_file())

    def test_wrong_recipient_fingerprint_is_rejected(self):
        recipient_private = x25519.X25519PrivateKey.generate()
        recipient_public = recipient_private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                mod.encrypt_snapshot(
                    snapshot=self.snapshot(),
                    recipient_b64=base64.b64encode(recipient_public).decode("ascii"),
                    recipient_key_id="sha256:" + "0" * 64,
                    run_id="12345",
                    output_dir=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()
