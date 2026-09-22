from __future__ import annotations

from pathlib import Path
import json
import tempfile
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

    def test_conflict_diagnostic_is_written_before_exact_gate(self):
        conflicts = [
            {
                "runtime_id": "crw_amat_15m_selected",
                "symbol": "AMAT",
                "timestamp": "2026-09-18T08:00:00+00:00",
                "fields": {
                    "close": {
                        "canonical_forward": 100.0,
                        "validated_seed": 101.0,
                        "seed_minus_canonical": 1.0,
                    }
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflicts.json"
            node = mod.write_conflict_diagnostic(
                conflicts=conflicts,
                expected_tokens=["MNQ@2026-09-16T16:59:00+00:00"],
                expected_public_run_id="35407829303",
                output_path=path,
            )
            self.assertTrue(path.is_file())
            self.assertEqual(node["schema"], "mmibkr.signal_history_conflict_diagnostic.v1")
            self.assertEqual(node["conflict_count"], 1)
            self.assertEqual(node["conflicts_by_symbol"], {"AMAT": 1})
            self.assertFalse(node["expected_conflict_set_match"])
            self.assertFalse(node["market_data_cache_mutated"])
            self.assertFalse(node["artifact_bars_written_to_real_cache"])
            self.assertFalse(node["broker_action"])
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                written["conflicts"][0]["fields"]["close"]["seed_minus_canonical"],
                1.0,
            )

        text = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(
            text.index("write_conflict_diagnostic("),
            text.index("validate_expected_conflicts(conflicts, expected_conflicts)"),
        )

    def test_workflow_publishes_sanitized_conflict_diagnostic_even_on_gate_failure(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  signal_history_reconciliation:"):]
        self.assertIn("--conflicts-output /diagnostic/conflicts.json", section)
        self.assertIn("- name: Publish sanitized signal-history conflict diagnostic", section)
        self.assertIn("if: ${{ always() }}", section)
        self.assertIn("mmibkr.signal_history_conflict_diagnostic.v1", section)
        self.assertIn("rendezvous/diagnostics", section)
        self.assertIn("MMIBKR_SIGNAL_HISTORY_CONFLICTS_BY_SYMBOL", section)

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
