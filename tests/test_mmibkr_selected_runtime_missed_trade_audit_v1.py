from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mmibkr_selected_runtime_missed_trade_audit_v1.py"
spec = importlib.util.spec_from_file_location("audit", MODULE_PATH)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)


class MissedTradeAuditContractTests(unittest.TestCase):
    def test_timezone_required(self):
        with self.assertRaisesRegex(ValueError, "must_be_timezone_aware"):
            audit.parse_utc("2026-09-20T07:38:42", field="start")

    def test_missing_inventory_never_becomes_authoritative(self):
        state = audit._inventory_state({"inventory_by_runtime": {}}, "crw_amat_15m_selected")
        self.assertFalse(state["authoritative_position"])
        self.assertIsNone(state["position_qty"])
        self.assertFalse(state["bot_owned_inventory_inferred_from_account_positions"])

    def test_entry_candidate_classification(self):
        evaluation = {
            "actionable_signal": True,
            "meta": {
                "signal_kind": "entry_long",
                "conditions": {
                    "current_values": {"CRW_SCORE": -3.0},
                    "parameters": {"entryLevel": -2.8, "exitLevel": 4.5},
                    "entry_long": {"passed": True, "items": []},
                    "exit_long": {"passed": False, "items": []},
                    "scale_long": {"passed": False, "items": []},
                },
            },
        }
        result = audit.classify_decision(
            evaluation=evaluation,
            diagnostic_evaluation=evaluation,
            generic_filter_blocked=False,
            warmup_ready=True,
        )
        self.assertEqual(result, "ENTRY_CANDIDATE")

    def test_signal_filter_blocked_classification(self):
        diagnostic = {
            "actionable_signal": True,
            "meta": {
                "signal_kind": "entry_long",
                "conditions": {
                    "entry_long": {"passed": True, "items": []},
                    "exit_long": {"passed": False, "items": []},
                    "scale_long": {"passed": False, "items": []},
                },
            },
        }
        result = audit.classify_decision(
            evaluation=None,
            diagnostic_evaluation=diagnostic,
            generic_filter_blocked=True,
            warmup_ready=True,
        )
        self.assertEqual(result, "SIGNAL_FILTER_BLOCKED")

    def test_warmup_has_precedence(self):
        result = audit.classify_decision(
            evaluation={"actionable_signal": True},
            diagnostic_evaluation={"actionable_signal": True},
            generic_filter_blocked=False,
            warmup_ready=False,
        )
        self.assertEqual(result, "WARMUP_INCOMPLETE")

    def test_paper_eligibility_fails_closed_without_inventory(self):
        result = audit.deterministic_paper_eligibility(
            binding={"execution_policy": {"paper_submit_enabled": True}},
            evaluation={
                "actionable_signal": True,
                "side": "BUY",
                "meta": {"signal_kind": "entry_long"},
            },
            inventory={"authoritative_position": False},
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["state"], "BOT_INVENTORY_AUTHORITY_REQUIRED")

    def test_futures_source_cache_candidate_uses_execution_month(self):
        paths = audit._source_cache_candidates(
            Path("/tmp/data"),
            {
                "instrument_class": "FUT",
                "symbol": "MNQ",
                "execution_contract": {
                    "lastTradeDateOrContractMonth": "20261218",
                },
            },
            "1Min",
        )
        self.assertIn(
            Path("/tmp/data/futures/MNQ-202612/1Min.csv"),
            paths,
        )

    def test_seed_prefix_preserves_restored_overlap(self):
        import pandas as pd

        restored = pd.DataFrame({
            "timestamp": pd.to_datetime(
                ["2026-09-16T00:02:00Z", "2026-09-16T00:03:00Z"],
                utc=True,
            ),
            "open": [20.0, 30.0],
            "high": [21.0, 31.0],
            "low": [19.0, 29.0],
            "close": [20.5, 30.5],
            "volume": [200, 300],
        })
        seed = [
            {
                "symbol": "MNQ",
                "bar_size": "1 min",
                "timestamp": "2026-09-16T00:00:00Z",
                "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10,
            },
            {
                "symbol": "MNQ",
                "bar_size": "1 min",
                "timestamp": "2026-09-16T00:02:00Z",
                "open": 999.0, "high": 999.0, "low": 999.0, "close": 999.0, "volume": 999,
            },
        ]
        combined, count = audit._prepend_seed_history(
            restored,
            seed_rows=seed,
            symbol="MNQ",
            source_timeframe="1Min",
            source=Path("/tmp/seed.jsonl"),
        )
        self.assertEqual(count, 1)
        self.assertEqual(len(combined), 3)
        overlap = combined.loc[
            combined["timestamp"] == pd.Timestamp("2026-09-16T00:02:00Z"),
            "close",
        ].iloc[0]
        self.assertEqual(float(overlap), 20.5)

    def test_summary_reports_stale_runtime_filter_latest(self):
        summary = audit._summary([
            {
                "runtime_id": "crw_amat_15m_selected",
                "decision": "NO_SIGNAL",
                "latest_bar_decision": "SIGNAL_FILTER_BLOCKED",
                "filter_latest_bar_truth": {
                    "runtime_filtered_latest_is_stale": True,
                },
                "latest_bar_would_have_reached_paper_quote_stage": False,
                "actual_owner_present": False,
            }
        ])
        node = summary["crw_amat_15m_selected"]
        self.assertEqual(node["runtime_filtered_latest_stale"], 1)
        self.assertEqual(node["latest_bar_signal_filter_blocked"], 1)

    def test_public_summary_excludes_rows(self):
        summary = audit.render_public_summary(
            {
                "ok": True,
                "audit_id": "audit-1",
                "private_source_sha": "d" * 40,
                "window": {"start_utc": "x", "end_utc": "y"},
                "runtime_count": 3,
                "row_count": 10,
                "candidate_row_count": 2,
                "owner_gap_candidate_count": 1,
                "summary": {"runtime": {"boundaries": 10}},
                "safety": {"read_only": True},
                "rows": [{"secret": "detail"}],
            }
        )
        self.assertNotIn("rows", summary)
        self.assertFalse(summary["detailed_rows_published"])


if __name__ == "__main__":
    unittest.main()
