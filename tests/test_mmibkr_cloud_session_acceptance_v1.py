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
            "public_head": "1" * 40,
            "private_head": mod.CANONICAL_PRIVATE_SHA,
            "live_execution_allowed": False,
            "credentials_included": False,
            "account_state_included": False,
            "positions_included": False,
            "orders_included": False,
            "checkpoint_restored": restored,
            "checkpoint_restored_sha256": "a" * 64 if restored else None,
            "checkpoint_restored_cache_key": "mmibkr-selected-runtime-cloud-checkpoint-v1-prev-d81" if restored else None,
            "checkpoint_cache_ready": True,
            "checkpoint_cache_saved": True,
            "checkpoint_cache_sha256": "b" * 64,
            "checkpoint_cache_key": "mmibkr-selected-runtime-cloud-checkpoint-v1-current-d81",
            "operator_snapshot_publish": {
                "status": "accepted",
                "runtime_count": 3,
                "positions_count": 1,
                "durable_readback_verified": True,
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

        current = self.good_receipt(restored=True)
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = current["checkpoint_restored_sha256"]
        previous["checkpoint_cache_key"] = current["checkpoint_restored_cache_key"]
        accepted = mod.evaluate(
            current,
            require_checkpoint_restored=True,
            previous_receipt=previous,
        )
        self.assertTrue(accepted["accepted"])
        self.assertTrue(accepted["checks"]["predecessor_receipt_accepted"])
        self.assertTrue(accepted["checks"]["predecessor_checkpoint_identity"])

    def test_rejects_wrong_runtime_count_or_source(self):
        node = self.good_receipt(restored=True)
        node["operator_snapshot_publish"]["runtime_count"] = 2
        node["private_head"] = "0" * 40
        result = mod.evaluate(node, require_checkpoint_restored=False)
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
                result = mod.evaluate(node, require_checkpoint_restored=False)
                self.assertFalse(result["accepted"])
                self.assertFalse(result["checks"]["operator_safety"])

    def test_rejects_missing_cache_persistence(self):
        node = self.good_receipt(restored=True)
        node["checkpoint_cache_saved"] = False
        result = mod.evaluate(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_cache_saved"])

    def test_steady_state_rejects_stale_or_wrong_predecessor_cache(self):
        current = self.good_receipt(restored=True)
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = "c" * 64
        previous["checkpoint_cache_key"] = "wrong-cache-key"
        result = mod.evaluate(
            current,
            require_checkpoint_restored=True,
            previous_receipt=previous,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["predecessor_checkpoint_identity"])

    def test_steady_state_rejects_unaccepted_predecessor_receipt(self):
        current = self.good_receipt(restored=True)
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = current["checkpoint_restored_sha256"]
        previous["checkpoint_cache_key"] = current["checkpoint_restored_cache_key"]
        previous["operator_snapshot_publish"]["status"] = "failed"
        result = mod.evaluate(
            current,
            require_checkpoint_restored=True,
            previous_receipt=previous,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["predecessor_receipt_accepted"])
        self.assertTrue(result["checks"]["predecessor_checkpoint_identity"])

    def test_rejects_nonhex_checkpoint_digest_identity(self):
        current = self.good_receipt(restored=True)
        current["checkpoint_restored_sha256"] = "z" * 64
        current["checkpoint_cache_sha256"] = "y" * 64
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = current["checkpoint_restored_sha256"]
        previous["checkpoint_cache_key"] = current["checkpoint_restored_cache_key"]
        result = mod.evaluate(
            current,
            require_checkpoint_restored=True,
            previous_receipt=previous,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_restored_identity_reported"])
        self.assertFalse(result["checks"]["checkpoint_saved_identity_reported"])

    def test_optional_public_head_expectation_fail_closes(self):
        node = self.good_receipt(restored=False)
        accepted = mod.evaluate(
            node,
            require_checkpoint_restored=False,
            expected_public_sha="1" * 40,
        )
        self.assertTrue(accepted["accepted"])
        rejected = mod.evaluate(
            node,
            require_checkpoint_restored=False,
            expected_public_sha="2" * 40,
        )
        self.assertFalse(rejected["accepted"])
        self.assertFalse(rejected["checks"]["public_head_expected"])

    def test_rejects_unverified_operator_durable_readback(self):
        node = self.good_receipt(restored=False)
        node["operator_snapshot_publish"]["durable_readback_verified"] = False
        result = mod.evaluate(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["operator_durable_readback"])


if __name__ == "__main__":
    unittest.main()
