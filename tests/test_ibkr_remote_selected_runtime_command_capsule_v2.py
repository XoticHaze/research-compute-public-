import base64
import hashlib
import json
import unittest

from scripts import ibkr_remote_selected_runtime_command_capsule_v2 as mod


class SelectedRuntimeCommandCapsuleV2Tests(unittest.TestCase):
    def recipient(self):
        raw = bytes(range(32))
        return {
            "schema": mod.RETURN_RECIPIENT_SCHEMA,
            "recipient_b64": base64.b64encode(raw).decode("ascii"),
            "recipient_key_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
        }

    def capsule(self):
        return {
            "schema": mod.CAPSULE_SCHEMA,
            "mode": mod.MODE,
            "source": {
                "repository": "XoticHaze/mm-IBKR",
                "head": "a" * 40,
                "archive_url": "https://api.github.com/repos/XoticHaze/mm-IBKR/tarball/" + "a" * 40,
                "archive_sha256": "b" * 64,
                "authorization_bearer": "source-capability-1234567890",
            },
            "request": {
                "command_id": "sha256:" + "c" * 64,
                "source_ref": "selected-runtime-event:abc",
                "canonical_submit_payload": {
                    "runtime_id": "mnq-runtime",
                    "symbol": "MNQ",
                    "action": "BUY",
                    "quantity": 1,
                    "order_type": "LMT",
                    "limit_price": 22000.0,
                    "session_mode": "FUTURES",
                    "idempotency_key": "proof-abc",
                },
                "selected_runtime_authority": {
                    "authority_source": "MM-IBKR selected_runtime.execution_policy",
                    "runtime_id": "mnq-runtime",
                    "strategy_id": "crw_score_multi_mode",
                    "strategy_spec_digest": "spec-1",
                    "symbol": "MNQ",
                    "timeframe": "12Min",
                    "paper_submit_enabled": True,
                    "live_submit_enabled": False,
                },
            },
            "cleanup": {
                "cancel_open_order": True,
                "flatten_filled_position": True,
                "require_zero_baseline": True,
                "allow_global_cancel": False,
            },
            "return_recipient": self.recipient(),
        }

    def validate(self, node):
        return mod.validate_capsule(json.dumps(node).encode())

    def test_v2_contains_no_broker_credential_field(self):
        node = self.capsule()
        out = self.validate(node)
        self.assertNotIn("ibkr", out)
        self.assertEqual(out["mode"], "paper_submit_proof")
        self.assertEqual(out["request"]["command_id"], "sha256:" + "c" * 64)
        self.assertEqual(out["return_recipient"]["recipient_key_id"], self.recipient()["recipient_key_id"])

    def test_legacy_ibkr_credentials_are_rejected_as_extra_capsule_field(self):
        node = self.capsule()
        node["ibkr"] = {"username": "paper", "password": "secret", "trading_mode": "paper"}
        with self.assertRaisesRegex(RuntimeError, "field set mismatch"):
            self.validate(node)

    def test_return_recipient_is_required_and_fingerprint_bound(self):
        node = self.capsule()
        del node["return_recipient"]
        with self.assertRaisesRegex(RuntimeError, "field set mismatch"):
            self.validate(node)
        node = self.capsule()
        node["return_recipient"]["recipient_key_id"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
            self.validate(node)

    def test_live_authority_is_rejected_recursively(self):
        node = self.capsule()
        node["request"]["canonical_submit_payload"]["nested"] = {"enable_live_trading": True}
        with self.assertRaisesRegex(RuntimeError, "live authority rejected"):
            self.validate(node)

    def test_runtime_identity_must_match_payload(self):
        node = self.capsule()
        node["request"]["canonical_submit_payload"]["runtime_id"] = "other"
        with self.assertRaisesRegex(RuntimeError, "payload runtime id mismatch"):
            self.validate(node)

    def test_cleanup_must_be_exact_and_global_cancel_false(self):
        node = self.capsule()
        node["cleanup"]["allow_global_cancel"] = True
        with self.assertRaisesRegex(RuntimeError, "cleanup contract mismatch"):
            self.validate(node)
        node = self.capsule()
        node["cleanup"]["flatten_filled_position"] = False
        with self.assertRaisesRegex(RuntimeError, "cleanup contract mismatch"):
            self.validate(node)

    def test_selected_runtime_must_be_paper_only(self):
        node = self.capsule()
        node["request"]["selected_runtime_authority"]["live_submit_enabled"] = True
        with self.assertRaisesRegex(RuntimeError, "live authority rejected"):
            self.validate(node)
        node = self.capsule()
        node["request"]["selected_runtime_authority"]["paper_submit_enabled"] = False
        with self.assertRaisesRegex(RuntimeError, "paper authority required"):
            self.validate(node)


if __name__ == "__main__":
    unittest.main()
