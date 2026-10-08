from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from scripts import mmibkr_cloud_session_acceptance_v1 as mod

# Synthetic IDs are CI fixtures only. Production IDs are always sourced from
# exact private MM selected_runtime_universe_14tu.json by the R5/R6 workflow.
TEST_EXPECTED_RUNTIME_IDS = ["test_amat_selected", "test_aph_selected", "test_mnq_selected"]

def _evaluate_with_ids(*args, **kwargs):
    kwargs.setdefault("expected_runtime_ids", TEST_EXPECTED_RUNTIME_IDS)
    return mod.evaluate(*args, **kwargs)



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
            "initial_backfill_ingest": {
                "ready": True,
                "performed_this_run": False,
                "public_run_id": mod.EXPECTED_INITIAL_BACKFILL_RUN_ID,
                "artifact_name": mod.EXPECTED_INITIAL_BACKFILL_ARTIFACT,
                "broker_action": False,
                "runtime_execution_contract_mutated": False,
                "live_execution_allowed": False,
                "preowner_checkpoint_saved": True,
                "preowner_checkpoint_sha256": "d" * 64,
                "preowner_checkpoint_cache_key": (
                    mod.CHECKPOINT_CACHE_PREFIX + "35699999999-d81-initial-backfill-preowner"
                ),
            },
            "last_cycle": {
                "boundary_key": "bar|test_mnq_selected",
                "boundary_run_id": "RUN_1",
            },
            "operator_snapshot_stream_publish_count": 2,
            "operator_snapshot_stream_attempt_count": 2,
            "operator_snapshot_publish": {
                "status": "accepted",
                "runtime_count": 3,
                "received_runtime_count": 3,
                "runtime_merge_applied": False,
                "runtime_ids": TEST_EXPECTED_RUNTIME_IDS,
                "boundary_run_id": "RUN_1",
                "source_sha": mod.CANONICAL_PRIVATE_SHA,
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
        result = _evaluate_with_ids(
            self.good_receipt(restored=False),
            require_checkpoint_restored=False,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["mode"], "first_post_fix")

    def test_steady_state_requires_prior_checkpoint_restore(self):
        result = _evaluate_with_ids(
            self.good_receipt(restored=False),
            require_checkpoint_restored=True,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_restored"])

        current = self.good_receipt(restored=True)
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = current["checkpoint_restored_sha256"]
        previous["checkpoint_cache_key"] = current["checkpoint_restored_cache_key"]
        accepted = _evaluate_with_ids(
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
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
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
                result = _evaluate_with_ids(node, require_checkpoint_restored=False)
                self.assertFalse(result["accepted"])
                self.assertFalse(result["checks"]["operator_safety"])

    def test_rejects_missing_canonical_backfill_checkpoint(self):
        node = self.good_receipt(restored=False)
        node["initial_backfill_ingest"]["preowner_checkpoint_saved"] = False
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["initial_backfill_preowner_checkpoint_saved"])

    def test_rejects_wrong_backfill_run_or_artifact(self):
        node = self.good_receipt(restored=False)
        node["initial_backfill_ingest"]["public_run_id"] = "wrong"
        node["initial_backfill_ingest"]["artifact_name"] = "wrong"
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["initial_backfill_public_run"])
        self.assertFalse(result["checks"]["initial_backfill_artifact"])

    def test_legacy_v1_requires_explicit_opt_in(self):
        node = self.good_receipt(restored=False)
        node["schema"] = mod.LEGACY_SCHEMA
        node.pop("initial_backfill_ingest")
        rejected = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(rejected["accepted"])
        self.assertFalse(rejected["checks"]["schema"])

        accepted = _evaluate_with_ids(
            node,
            require_checkpoint_restored=False,
            allow_legacy_v1=True,
        )
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["receipt_contract"], "legacy_v1")

    def test_declared_expected_predecessor_must_match_actual_restore(self):
        node = self.good_receipt(restored=True)
        node["expected_predecessor_checkpoint_cache_key"] = (
            mod.CHECKPOINT_CACHE_PREFIX + "35677937156-d81-backfill-checkpoint-acceptance"
        )
        node["expected_predecessor_checkpoint_sha256"] = "a" * 64
        node["expected_predecessor_checkpoint_match"] = True
        node["checkpoint_restored_cache_key"] = node[
            "expected_predecessor_checkpoint_cache_key"
        ]
        node["checkpoint_restored_sha256"] = node[
            "expected_predecessor_checkpoint_sha256"
        ]

        accepted = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertTrue(accepted["accepted"])
        self.assertTrue(accepted["checks"]["expected_predecessor_identity_reported"])
        self.assertTrue(accepted["checks"]["expected_predecessor_restore_match"])

        node["checkpoint_restored_sha256"] = "b" * 64
        rejected = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(rejected["accepted"])
        self.assertFalse(rejected["checks"]["expected_predecessor_restore_match"])

    def test_declared_expected_predecessor_requires_key_and_sha(self):
        node = self.good_receipt(restored=True)
        node["expected_predecessor_checkpoint_cache_key"] = (
            mod.CHECKPOINT_CACHE_PREFIX + "expected"
        )
        node["expected_predecessor_checkpoint_sha256"] = ""
        node["expected_predecessor_checkpoint_match"] = True
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["expected_predecessor_identity_reported"])

    def test_required_terminal_continuity_must_be_ready_and_nonempty(self):
        node = self.good_receipt(restored=True)
        node["expected_predecessor_checkpoint_cache_key"] = (
            mod.CHECKPOINT_CACHE_PREFIX + "successor"
        )
        node["expected_predecessor_checkpoint_sha256"] = "a" * 64
        node["expected_predecessor_checkpoint_match"] = True
        node["checkpoint_restored_cache_key"] = node[
            "expected_predecessor_checkpoint_cache_key"
        ]
        node["checkpoint_restored_sha256"] = node[
            "expected_predecessor_checkpoint_sha256"
        ]
        node["predecessor_terminal_continuity_required"] = True
        node["predecessor_terminal_continuity_ready"] = True
        node["predecessor_terminal_continuity_entry_count"] = 5

        accepted = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertTrue(accepted["accepted"])
        self.assertTrue(
            accepted["checks"]["predecessor_terminal_continuity_ready"]
        )
        self.assertTrue(
            accepted["checks"]["predecessor_terminal_continuity_has_exact_restore"]
        )

        node["predecessor_terminal_continuity_entry_count"] = 0
        rejected = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(rejected["accepted"])
        self.assertFalse(
            rejected["checks"]["predecessor_terminal_continuity_ready"]
        )

    def test_required_terminal_continuity_rejects_unmatched_predecessor(self):
        node = self.good_receipt(restored=True)
        node["predecessor_terminal_continuity_required"] = True
        node["predecessor_terminal_continuity_ready"] = True
        node["predecessor_terminal_continuity_entry_count"] = 1
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(
            result["checks"]["predecessor_terminal_continuity_has_exact_restore"]
        )

    def test_rejects_missing_cache_persistence(self):
        node = self.good_receipt(restored=True)
        node["checkpoint_cache_saved"] = False
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_cache_saved"])

    def test_steady_state_rejects_stale_or_wrong_predecessor_cache(self):
        current = self.good_receipt(restored=True)
        previous = self.good_receipt(restored=False)
        previous["checkpoint_cache_sha256"] = "c" * 64
        previous["checkpoint_cache_key"] = "wrong-cache-key"
        result = _evaluate_with_ids(
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
        result = _evaluate_with_ids(
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
        result = _evaluate_with_ids(
            current,
            require_checkpoint_restored=True,
            previous_receipt=previous,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["checkpoint_restored_identity_reported"])
        self.assertFalse(result["checks"]["checkpoint_saved_identity_reported"])

    def test_optional_public_head_expectation_fail_closes(self):
        node = self.good_receipt(restored=False)
        accepted = _evaluate_with_ids(
            node,
            require_checkpoint_restored=False,
            expected_public_sha="1" * 40,
        )
        self.assertTrue(accepted["accepted"])
        rejected = _evaluate_with_ids(
            node,
            require_checkpoint_restored=False,
            expected_public_sha="2" * 40,
        )
        self.assertFalse(rejected["accepted"])
        self.assertFalse(rejected["checks"]["public_head_expected"])

    def test_rejects_unverified_operator_durable_readback(self):
        node = self.good_receipt(restored=False)
        node["operator_snapshot_publish"]["durable_readback_verified"] = False
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["operator_durable_readback"])

    def test_rejects_session_without_successful_cycle_snapshot_stream(self):
        node = self.good_receipt(restored=False)
        node["operator_snapshot_stream_publish_count"] = 0
        node["operator_snapshot_stream_attempt_count"] = 3
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["operator_stream_publish"])

    def test_rejects_impossible_stream_attempt_accounting(self):
        node = self.good_receipt(restored=False)
        node["operator_snapshot_stream_publish_count"] = 3
        node["operator_snapshot_stream_attempt_count"] = 2
        result = _evaluate_with_ids(node, require_checkpoint_restored=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["operator_stream_attempts"])


if __name__ == "__main__":
    unittest.main()
