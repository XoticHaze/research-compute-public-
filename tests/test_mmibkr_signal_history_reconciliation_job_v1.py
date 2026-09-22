from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class SignalHistoryReconciliationJobTests(unittest.TestCase):
    def test_dedicated_route_and_concurrency_are_isolated_from_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "rendezvous/fire/mmibkr-selected-runtime-cloud-signal-history-reconciliation-r1",
            text,
        )
        self.assertIn('mode="signal_history_reconciliation"', text)
        self.assertIn(
            "needs.route.outputs.mode == 'signal_history_reconciliation'",
            text,
        )
        self.assertIn(
            "group: mmibkr-selected-runtime-cloud-signal-history-reconciliation-r1",
            text,
        )

    def test_exact_predecessor_and_exact_conflict_set_are_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  signal_history_reconciliation:"):]
        self.assertIn("expected_checkpoint_cache_key", section)
        self.assertIn("expected_checkpoint_sha256", section)
        self.assertIn("expected_conflicts", section)
        self.assertIn("fail-on-cache-miss: true", section)
        self.assertIn('test "$CACHE_HIT" = \'true\'', section)
        self.assertIn('test "$RESTORED_CACHE_KEY" = "$EXPECTED_CACHE_KEY"', section)
        self.assertIn('test "$actual" = "$EXPECTED_SHA256"', section)
        self.assertIn("--expected-conflicts-json /input/expected-conflicts.json", section)

    def test_clean_seed_validation_precedes_metadata_only_reconciliation(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  signal_history_reconciliation:"):]
        seed = section.index(
            "- name: Validate seed independently on isolated clean data root"
        )
        reconcile = section.index(
            "- name: Reconcile signal-history metadata without rewriting forward bars"
        )
        checkpoint = section.index(
            "- name: Build reconciled terminal-plus-signal checkpoint"
        )
        self.assertLess(seed, reconcile)
        self.assertLess(reconcile, checkpoint)
        self.assertIn(
            "selected_runtime_initial_backfill_ingest_v1.py",
            section[seed:reconcile],
        )
        self.assertIn("--data-root /seed-data", section[seed:reconcile])
        self.assertIn(
            "mmibkr_signal_history_metadata_reconcile_v1.py",
            section[reconcile:checkpoint],
        )
        self.assertIn("market_data_cache_mutated", section[reconcile:checkpoint])
        self.assertIn("artifact_bars_written_to_real_cache", section[reconcile:checkpoint])

    def test_reconciled_checkpoint_requires_terminal_and_signal_metadata(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  signal_history_reconciliation:"):]
        self.assertIn("signal_history_contract_index_included", section)
        self.assertIn("terminal_boundary_continuity_included", section)
        self.assertIn("reconciled checkpoint missing signal-history index", section)
        self.assertIn("reconciled checkpoint missing terminal continuity", section)
        self.assertIn("- name: Save reconciled checkpoint", section)
        self.assertIn("- name: Delete local reconciled checkpoint before readback", section)
        self.assertIn("- name: Restore exact reconciled checkpoint", section)
        self.assertIn("- name: Verify reconciled checkpoint round-trip", section)

    def test_reconciliation_receipt_preserves_safety_and_discrepancy_evidence(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  signal_history_reconciliation:"):]
        self.assertIn("mmibkr.signal_history_reconciliation_receipt.v1", section)
        self.assertIn("'conflicts': result.get('conflicts')", section)
        self.assertIn("'conflict_policy': result.get('conflict_policy')", section)
        self.assertIn("'market_data_cache_mutated': False", section)
        self.assertIn("'artifact_bars_written_to_real_cache': False", section)
        self.assertIn("'paper_owner_started': False", section)
        self.assertIn("'execution_authority_mutated': False", section)
        self.assertIn("'live_execution_allowed': False", section)


if __name__ == "__main__":
    unittest.main()
