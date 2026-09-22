from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class SuccessorRestoreAcceptanceJobTests(unittest.TestCase):
    def test_route_selects_successor_restore_acceptance(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "rendezvous/fire/mmibkr-selected-runtime-cloud-successor-restore-acceptance-r1",
            text,
        )
        self.assertIn('mode="successor_restore_acceptance"', text)
        self.assertIn(
            "needs.route.outputs.mode == 'successor_restore_acceptance'",
            text,
        )
        self.assertIn(
            "group: mmibkr-selected-runtime-cloud-successor-restore-acceptance-r1",
            text,
        )

    def test_exact_cache_and_sha_are_required_before_restore(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  successor_restore_acceptance:"):]
        self.assertIn("expected_checkpoint_cache_key", section)
        self.assertIn("expected_checkpoint_sha256", section)
        self.assertIn("fail-on-cache-miss: true", section)
        self.assertIn('test "$CACHE_HIT" = \'true\'', section)
        self.assertIn('test "$RESTORED_CACHE_KEY" = "$EXPECTED_CACHE_KEY"', section)
        self.assertIn('test "$actual" = "$EXPECTED_SHA256"', section)
        self.assertIn("MMIBKR_SUCCESSOR_RESTORE_EXACT_CACHE_HIT=1", section)

    def test_private_canonical_restore_and_rebuild_are_executed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  successor_restore_acceptance:"):]
        self.assertIn(
            "python scripts/operator/runtime_market_data_cache_checkpoint_v1.py",
            section,
        )
        self.assertIn("--restore-archive /checkpoint/latest.tgz", section)
        self.assertIn("--manifest-output /verify/restored-plan.json", section)
        self.assertIn("--archive-output /verify/rebuilt.tgz", section)
        self.assertIn("restored checkpoint plan incomplete", section)
        self.assertIn("restored checkpoint symbol coverage incomplete", section)
        self.assertIn("signal_history_contract_index_included", section)

    def test_signal_history_identity_is_validated_without_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  successor_restore_acceptance:"):]
        self.assertIn(
            "mmibkr.selected_runtime_signal_history_contracts.v1",
            section,
        )
        self.assertIn("restored signal-history public run mismatch", section)
        self.assertIn("restored signal-history runtime count mismatch", section)
        self.assertIn("restored signal-history warmup not ready", section)
        self.assertIn("docker run --rm -i", section)
        self.assertNotIn("selected_runtime_cloud_daemon_v1.py", section)
        self.assertIn("'paper_owner_started': False", section)
        self.assertIn("'broker_action': False", section)
        self.assertIn("'live_execution_allowed': False", section)

    def test_sanitized_restore_receipt_is_durable(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  successor_restore_acceptance:"):]
        self.assertIn("mmibkr.successor_restore_acceptance.v1", section)
        self.assertIn("'exact_cache_key_restored': True", section)
        self.assertIn("'exact_sha256_verified_before_restore': True", section)
        self.assertIn("'canonical_restore_executed': True", section)
        self.assertIn("'canonical_checkpoint_plan_rebuilt': True", section)
        self.assertIn("'signal_history_index_validated': True", section)
        self.assertIn("'private_source_included': False", section)
        self.assertIn("'account_state_included': False", section)
        self.assertIn("'positions_included': False", section)
        self.assertIn("'orders_included': False", section)


if __name__ == "__main__":
    unittest.main()
