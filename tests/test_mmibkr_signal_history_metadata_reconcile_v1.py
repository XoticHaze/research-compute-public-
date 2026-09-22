from __future__ import annotations

from pathlib import Path
import unittest

from scripts import mmibkr_signal_history_metadata_reconcile_v1 as mod


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mmibkr_signal_history_metadata_reconcile_v1.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class SignalHistoryMetadataReconcileTests(unittest.TestCase):
    def test_expected_conflict_set_is_exact(self):
        conflicts = [
            {
                "symbol": "MNQ",
                "timestamp": "2026-09-16T16:59:00+00:00",
                "fields": {"close": {}},
            },
            {
                "symbol": "MNQ",
                "timestamp": "2026-09-17T16:59:00+00:00",
                "fields": {"volume": {}},
            },
        ]
        mod.validate_expected_conflicts(
            conflicts,
            [
                "MNQ@2026-09-16T16:59:00+00:00",
                "MNQ@2026-09-17T16:59:00+00:00",
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "conflict_set_mismatch"):
            mod.validate_expected_conflicts(
                conflicts,
                ["MNQ@2026-09-16T16:59:00+00:00"],
            )

    def test_reconciliation_requires_explicit_conflicts(self):
        with self.assertRaisesRegex(RuntimeError, "expected_conflicts_required"):
            mod.validate_expected_conflicts([], [])

    def test_helper_is_metadata_only_for_real_cache(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            '"conflict_policy": "preserve_existing_canonical_forward_cache"',
            text,
        )
        self.assertIn('"market_data_cache_mutated": False', text)
        self.assertIn('"artifact_bars_written_to_real_cache": False', text)
        self.assertIn('"execution_authority_mutated": False', text)
        self.assertIn('"broker_action": False', text)
        self.assertIn('"live_execution_allowed": False', text)
        self.assertNotIn("._save_csvs(", text)
        self.assertNotIn("._safe_save(", text)

    def test_private_authority_checks_are_required_before_index_write(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("build_active_runtime_bindings", text)
        self.assertIn("build_repo_warmup_contract", text)
        self.assertIn("contract_digest", text)
        self.assertIn("resolve_signal_history_contract", text)
        self.assertIn("execution_digest_mismatch", text)
        self.assertIn("real_cache_warmup_incomplete", text)
        self.assertIn("projected_digest_mismatch", text)
        self.assertLess(
            text.index("validate_expected_conflicts(conflicts, expected_conflicts)"),
            text.index("os.replace(temp, target_index)"),
        )


if __name__ == "__main__":
    unittest.main()
