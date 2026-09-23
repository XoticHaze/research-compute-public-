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

    def test_persistent_execute_mode_requires_no_automatic_cleanup(self):
        node = self.capsule()
        node["mode"] = mod.EXECUTE_MODE
        node["cleanup"] = {
            "cancel_open_order": False,
            "flatten_filled_position": False,
            "require_zero_baseline": False,
            "allow_global_cancel": False,
        }
        out = self.validate(node)
        self.assertEqual(out["mode"], mod.EXECUTE_MODE)
        self.assertFalse(out["cleanup"]["cancel_open_order"])
        self.assertFalse(out["cleanup"]["flatten_filled_position"])
        self.assertFalse(out["cleanup"]["require_zero_baseline"])
        self.assertFalse(out["cleanup"]["allow_global_cancel"])

        node = self.capsule()
        node["mode"] = mod.EXECUTE_MODE
        with self.assertRaisesRegex(RuntimeError, "persistent paper execute cleanup contract mismatch"):
            self.validate(node)

    def test_paper_account_hygiene_mode_requires_flat_strategy_inventory_and_explicit_operator_ack(self):
        node = self.capsule()
        node["mode"] = mod.HYGIENE_MODE
        node["request"] = {
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "operator-snapshot:test",
            "expected_positions": [{
                "symbol": "AMAT",
                "conId": 123,
                "secType": "STK",
                "position": 325.0,
            }],
            "ownership_authority": {
                "schema": mod.HYGIENE_OWNERSHIP_SCHEMA,
                "operator_snapshot_sha256": "d" * 64,
                "snapshot_generated_at_utc": "2026-09-23T10:30:34Z",
                "runtime_source_sha": "a" * 40,
                "ownership_source": "selected_runtime_strategy_inventory_v1",
                "strategy_owned_positions": [],
                "account_position_count": 1,
                "operator_approved": True,
                "operator_ack": mod.HYGIENE_OPERATOR_ACK,
            },
            "execute": False,
            "batch_size": 5,
        }
        node["cleanup"] = {
            "cancel_open_order": False,
            "flatten_filled_position": False,
            "require_zero_baseline": False,
            "allow_global_cancel": False,
        }
        out = self.validate(node)
        self.assertEqual(out["mode"], mod.HYGIENE_MODE)
        self.assertFalse(out["request"]["execute"])
        self.assertEqual(out["request"]["expected_positions"][0]["position"], 325.0)

        bad = json.loads(json.dumps(node))
        bad["request"]["ownership_authority"]["strategy_owned_positions"] = [{"symbol": "AMAT"}]
        with self.assertRaisesRegex(RuntimeError, "requires flat selected-runtime"):
            self.validate(bad)

        bad = json.loads(json.dumps(node))
        bad["request"]["ownership_authority"]["operator_ack"] = "WRONG"
        with self.assertRaisesRegex(RuntimeError, "operator ack mismatch"):
            self.validate(bad)

    def test_attested_source_ticket_requires_no_private_bearer_or_url(self):
        node = self.capsule()
        node["source"] = {
            "repository": "XoticHaze/mm-IBKR",
            "head": "a" * 40,
            "archive_sha256": "b" * 64,
            "archive_bytes": 12345,
            "transport": mod.ATTESTED_SOURCE_TRANSPORT,
        }
        out = self.validate(node)
        self.assertEqual(
            out["source"]["transport"],
            "fleet_private_attested_source_v1",
        )
        self.assertNotIn("authorization_bearer", out["source"])
        self.assertNotIn("archive_url", out["source"])
        self.assertEqual(out["source"]["archive_bytes"], 12345)

    def test_attested_source_ticket_rejects_extra_bearer_capability(self):
        node = self.capsule()
        node["source"] = {
            "repository": "XoticHaze/mm-IBKR",
            "head": "a" * 40,
            "archive_sha256": "b" * 64,
            "archive_bytes": 12345,
            "transport": mod.ATTESTED_SOURCE_TRANSPORT,
            "authorization_bearer": "must-not-be-admitted",
        }
        with self.assertRaisesRegex(RuntimeError, "source ticket field set mismatch"):
            self.validate(node)

    def test_unknown_command_mode_is_rejected(self):
        node = self.capsule()
        node["mode"] = "paper_magic"
        with self.assertRaisesRegex(RuntimeError, "mode mismatch"):
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
