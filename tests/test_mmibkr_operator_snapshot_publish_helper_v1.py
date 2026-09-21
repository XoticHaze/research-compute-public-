from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from scripts import mmibkr_operator_snapshot_publish_v1 as mod


class OperatorSnapshotPublishHelperTests(unittest.TestCase):
    def snapshot(self) -> dict:
        return {
            "schema": mod.SNAPSHOT_SCHEMA,
            "mode": "paper",
            "live_enabled": False,
            "runtimes": [{"runtime_id": "a"}, {"runtime_id": "b"}, {"runtime_id": "c"}],
            "positions": [{"position": 1}],
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
        }

    def test_accepts_exact_sanitized_read_only_snapshot(self):
        mod.validate_snapshot(self.snapshot())

    def test_rejects_any_sensitive_or_mutating_authority(self):
        mutations = (
            ("privacy", "account_identifiers_included"),
            ("privacy", "credentials_included"),
            ("privacy", "tokens_included"),
            ("privacy", "private_source_included"),
            ("privacy", "execution_authority_included"),
            ("authority", "strategy_authority"),
            ("authority", "execution_policy_authority"),
            ("authority", "sizing_authority"),
            ("authority", "broker_mutation_authority"),
            ("authority", "live_execution_allowed"),
        )
        for group, key in mutations:
            with self.subTest(group=group, key=key):
                node = self.snapshot()
                node[group][key] = True
                with self.assertRaises(RuntimeError):
                    mod.validate_snapshot(node)

    def test_oidc_url_pins_operator_console_audience(self):
        url = mod.build_oidc_url("https://oidc.example/token?foo=bar")
        self.assertIn("foo=bar", url)
        self.assertIn("audience=mmibkr-operator-console", url)

    def test_publish_receipt_must_match_counts_and_durable_readback(self):
        receipt = {
            "ok": True,
            "schema": "mmibkr.operator_console_publish_receipt.v1",
            "received_runtime_count": 3,
            "runtime_count": 3,
            "stored_runtime_count": 3,
            "runtime_merge_applied": False,
            "positions_count": 1,
            "durable_readback_verified": True,
            "credentials_included": False,
            "tokens_included": False,
            "broker_mutation_authority": False,
            "live_execution_allowed": False,
        }
        result = mod.validate_publish_receipt(receipt, runtime_count=3, positions_count=1)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["received_runtime_count"], 3)
        self.assertEqual(result["runtime_count"], 3)
        self.assertFalse(result["runtime_merge_applied"])
        self.assertTrue(result["durable_readback_verified"])

        merged = dict(receipt)
        merged["received_runtime_count"] = 1
        merged["runtime_count"] = 1
        merged["stored_runtime_count"] = 3
        merged["runtime_merge_applied"] = True
        merged_result = mod.validate_publish_receipt(
            merged,
            runtime_count=1,
            positions_count=1,
        )
        self.assertEqual(merged_result["received_runtime_count"], 1)
        self.assertEqual(merged_result["runtime_count"], 3)
        self.assertTrue(merged_result["runtime_merge_applied"])

        for key, value in (
            ("received_runtime_count", 2),
            ("runtime_count", 2),
            ("stored_runtime_count", 2),
            ("positions_count", 0),
            ("durable_readback_verified", False),
            ("credentials_included", True),
            ("tokens_included", True),
            ("broker_mutation_authority", True),
            ("live_execution_allowed", True),
        ):
            with self.subTest(key=key):
                bad = dict(receipt)
                bad[key] = value
                with self.assertRaises(RuntimeError):
                    mod.validate_publish_receipt(bad, runtime_count=3, positions_count=1)

    def test_load_snapshot_rejects_oversize_and_nonobject(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.json"
            bad.write_text("[]", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                mod.load_snapshot(bad)

            huge = root / "huge.json"
            huge.write_bytes(b"{" + b"x" * mod.MAX_SNAPSHOT_BYTES + b"}")
            with self.assertRaises(RuntimeError):
                mod.load_snapshot(huge)

    def test_publish_receipt_rejects_stored_runtime_count_below_received(self):
        receipt = {
            "ok": True,
            "schema": "mmibkr.operator_console_publish_receipt.v1",
            "received_runtime_count": 3,
            "runtime_count": 3,
            "stored_runtime_count": 2,
            "runtime_merge_applied": True,
            "positions_count": 1,
            "durable_readback_verified": True,
            "credentials_included": False,
            "tokens_included": False,
            "broker_mutation_authority": False,
            "live_execution_allowed": False,
        }
        with self.assertRaises(RuntimeError):
            mod.validate_publish_receipt(
                receipt,
                runtime_count=3,
                positions_count=1,
            )

    def test_publish_receipt_rejects_legacy_runtime_count_mismatch(self):
        receipt = {
            "ok": True,
            "schema": "mmibkr.operator_console_publish_receipt.v1",
            "received_runtime_count": 1,
            "runtime_count": 3,
            "stored_runtime_count": 3,
            "runtime_merge_applied": True,
            "positions_count": 0,
            "durable_readback_verified": True,
            "credentials_included": False,
            "tokens_included": False,
            "broker_mutation_authority": False,
            "live_execution_allowed": False,
        }
        with self.assertRaises(RuntimeError):
            mod.validate_publish_receipt(
                receipt,
                runtime_count=1,
                positions_count=0,
            )


if __name__ == "__main__":
    unittest.main()
