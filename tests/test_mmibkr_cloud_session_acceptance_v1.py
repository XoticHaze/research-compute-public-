from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from scripts import mmibkr_cloud_session_acceptance_v1 as mod


class MMIBKRCloudSessionAcceptanceTests(unittest.TestCase):
    def good_receipt(self, *, restored: bool) -> dict:
        return {
            "schema": mod.SCHEMA,
            "ok": True,
            "session_accepted": True,
            "run_id": "35699999999",
            "private_head": mod.CANONICAL_PRIVATE_SHA,
            "live_execution_allowed": False,
            "credentials_included": False,
            "account_state_included": False,
            "positions_included": False,
            "orders_included": False,
            "checkpoint_restored": restored,
            "checkpoint_cache_ready": True,
            "checkpoint_cache_saved": True,
            "operator_snapshot_publish": {
                "status": "accepted",
                "runtime_count": 3,
                "positions_count": 1,
                "account_identifiers_included": False,
                "credentials_included": False,
                "tokens_included": False,
                "private_source_included": False,
                "execution_authority_included": False,
                "broker_mutation_authority": False,
                "live_execution_allowed": False,
            },
        }

    def test_first_post_fix_accepts_self_healed_start(self):
        result = mod.evaluate(
            self.good_receipt(restored=False),
            require_checkpoint_restored=False,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["mode"], "first_post_fix")

    def test_steady_state_requires_prior_checkpoint_restore(self):
        result = mod.evaluate(
            self.good_receipt(restored=False),
            require_checkpoint_restored=True,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_restored"])

        accepted = mod.evaluate(
            self.good_receipt(restored=True),
            require_checkpoint_restored=True,
        )
        self.assertTrue(accepted["accepted"])

    def test_rejects_wrong_runtime_count_or_source(self):
        node = self.good_receipt(restored=True)
        node["operator_snapshot_publish"]["runtime_count"] = 2
        node["private_head"] = "0" * 40
        result = mod.evaluate(node, require_checkpoint_restored=True)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["operator_runtime_count"])
        self.assertFalse(result["checks"]["private_head"])

    def test_rejects_any_publisher_authority_or_secret_flag(self):
        for key in (
            "account_identifiers_included",
            "credentials_included",
            "tokens_included",
            "private_source_included",
            "execution_authority_included",
            "broker_mutation_authority",
            "live_execution_allowed",
        ):
            with self.subTest(key=key):
                node = self.good_receipt(restored=True)
                node["operator_snapshot_publish"][key] = True
                result = mod.evaluate(node, require_checkpoint_restored=True)
                self.assertFalse(result["accepted"])
                self.assertFalse(result["checks"]["operator_safety"])

    def test_rejects_missing_cache_persistence(self):
        node = self.good_receipt(restored=True)
        node["checkpoint_cache_saved"] = False
        result = mod.evaluate(node, require_checkpoint_restored=True)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_cache_saved"])


if __name__ == "__main__":
    unittest.main()
