from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "config" / "ibkr_initial_selected_runtime_backfill_v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ibkr-cloudflare-readonly-b1-r1.yml"


class InitialSelectedRuntimeBackfillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = json.loads(REQUEST.read_text(encoding="utf-8"))
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_request_is_read_only_and_covers_active_runtime_sources(self):
        node = self.request
        self.assertFalse(node["broker_mutation"])
        self.assertFalse(node["runtime_execution_contract_mutation"])
        self.assertFalse(node["live_trading_change"])
        self.assertEqual(node["symbols"], ["AMAT", "APH", "MNQ"])
        self.assertEqual(set(node["bar_requests"]), {"AMAT", "APH", "MNQ"})

        required = node["required_completed_bars"]
        self.assertGreaterEqual(required["AMAT_target_15Min"], 400)
        self.assertGreaterEqual(required["APH_target_15Min"], 400)
        self.assertGreaterEqual(required["MNQ_target_12Min"], 400)
        self.assertGreaterEqual(required["MNQ_source_1Min"], 4800)

    def test_stock_first_pages_remain_canonical_two_week_15min_chunks(self):
        for symbol in ("AMAT", "APH"):
            rows = self.request["bar_requests"][symbol]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_timeframe"], "15Min")
            self.assertEqual(rows[0]["target_timeframe"], "15Min")
            self.assertEqual(rows[0]["bar_size_setting"], "15 mins")
            self.assertEqual(rows[0]["duration_str"], "2 W")

    def test_mnq_backfill_uses_mm_selected_december_signal_contract_and_bounded_one_day_chunks(self):
        contract = self.request["contracts"]["MNQ"]
        self.assertEqual(contract["symbol"], "MNQ")
        self.assertEqual(contract["secType"], "FUT")
        self.assertEqual(contract["exchange"], "CME")
        self.assertEqual(contract["currency"], "USD")
        self.assertEqual(contract["lastTradeDateOrContractMonth"], "202612")
        self.assertNotIn("conId", contract)

        rows = self.request["bar_requests"]["MNQ"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["source_timeframe"], "1Min")
        self.assertEqual(rows[0]["target_timeframe"], "12Min")
        self.assertEqual(rows[0]["bar_size_setting"], "1 min")
        self.assertTrue(all(row["duration_str"] == "1 D" for row in rows))
        explicit = [row.get("end_date_time_utc") for row in rows[1:]]
        self.assertEqual(explicit, [
            "2026-09-18T00:00:00Z",
            "2026-09-17T00:00:00Z",
            "2026-09-16T00:00:00Z",
            "2026-09-15T00:00:00Z",
        ])

    def test_one_shot_loader_does_not_change_normal_push_defaults(self):
        text = self.workflow
        self.assertIn(
            "POST_AUTH_SYMBOLS: \${{ github.event_name == 'workflow_dispatch' && inputs.symbols || 'AMAT,APH' }}",
            text,
        )
        self.assertIn(
            "POST_AUTH_CONTRACTS_JSON: \${{ github.event_name == 'workflow_dispatch' && inputs.contracts_json || '{}' }}",
            text,
        )
        self.assertIn(
            "POST_AUTH_BAR_REQUESTS_JSON: \${{ github.event_name == 'workflow_dispatch' && inputs.bar_requests_json || '' }}",
            text,
        )
        loader = text.index("name: Load one-shot selected-runtime initial backfill request")
        seal = text.index("name: Obtain one-run sealed gateway environment")
        self.assertLess(loader, seal)
        block = text[loader:seal]
        self.assertIn("[ibkr-initial-backfill]", block)
        self.assertIn("config/ibkr_initial_selected_runtime_backfill_v1.json", block)
        self.assertIn("IBKR_INITIAL_SELECTED_RUNTIME_BACKFILL=1", block)
        self.assertNotIn("placeOrder(", block)
        self.assertNotIn("reqGlobalCancel", block)


if __name__ == "__main__":
    unittest.main()
