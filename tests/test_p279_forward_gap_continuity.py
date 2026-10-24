"""Two focused funded-forward continuity cases, no network or broker access."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import pandas as pd

from research import p279_p249_p266_forward_shadow_observer_r1 as observer


class TestForwardGapContinuity(unittest.TestCase):
    def _run(self, prices: dict[str, list[float | None]]) -> dict:
        dates = pd.to_datetime([
            "2026-09-09", "2026-09-10", "2026-09-11",
            "2026-09-14", "2026-09-15",
        ])
        close = pd.DataFrame(prices, index=dates, dtype=float)
        frozen = {
            "p64": {}, "p36": {}, "p266": {},
            "p249_core": {"A": 0.5, "B": 0.5},
            "p249_plus_p266": {"A": 0.5, "B": 0.5},
        }
        out = io.StringIO()
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with (
                    patch.object(observer, "ALL", ["A", "B"]),
                    patch.object(observer, "DECISION_AT", pd.Timestamp("2026-09-10T07:25:00Z")),
                    patch.object(observer.yf, "download", return_value=close),
                    patch.object(observer, "_portfolio_weights", return_value=frozen),
                    redirect_stdout(out),
                ):
                    observer.main()
                with open("artifacts/p279_p249_p266_forward_shadow_observer_r1.json", encoding="utf-8") as fh:
                    return json.load(fh)
            finally:
                os.chdir(cwd)

    def test_missing_held_close_freezes_all_later_nav_until_backfilled(self):
        result = self._run({"A": [100, 101, 102, 103, 104], "B": [100, 101, None, 103, 104]})
        self.assertEqual(result["status"], "SOURCE_GAP_UNRESOLVED")
        self.assertFalse(result["forward"]["economic_continuity_verified"])
        self.assertEqual(result["source_health"]["unresolved_forward_gap"]["first_unresolved_session"], "2026-09-11")
        self.assertEqual(result["source_health"]["unresolved_forward_gap"]["missing_held_symbols"], ["B"])
        self.assertEqual([r["date"] for r in result["forward"]["observations"]], ["2026-09-10"])
        self.assertEqual(result["forward"]["latest_close"], "2026-09-10")

    def test_economic_current_publisher_rejects_gap_and_incomplete_receipts(self):
        from copy import deepcopy
        from research.forward_p249_p266_shadow_r1 import current_publication_admitted
        valid = {
            "schema": "research.forward_p249_p266_shadow_r1",
            "parent": "P249/P266/P278",
            "workload_id": "FORWARD_P249_P266_SHADOW_R1",
            "status": "FORWARD_OBSERVING",
            "source_health": {"unresolved_forward_gap": None, "latest_scored_common_session": "2026-09-10"},
            "forward": {
                "economic_continuity_verified": True, "latest_close": "2026-09-10",
                "observations": [{"date": "2026-09-10"}],
                "p249_core_net": {"days": 1}, "p249_plus_p266_net": {"days": 1},
            },
        }
        self.assertTrue(current_publication_admitted(valid))
        gap = deepcopy(valid)
        gap["status"] = "SOURCE_GAP_UNRESOLVED"
        gap["source_health"]["unresolved_forward_gap"] = {"first_unresolved_session": "2026-09-11"}
        gap["forward"]["economic_continuity_verified"] = False
        self.assertFalse(current_publication_admitted(gap))
        missing = deepcopy(valid)
        del missing["source_health"]["unresolved_forward_gap"]
        self.assertFalse(current_publication_admitted(missing))
        partial = deepcopy(valid)
        partial["forward"]["observations"] = []
        self.assertFalse(current_publication_admitted(partial))

    def test_complete_held_closes_continue_scoring(self):
        result = self._run({"A": [100, 101, 102, 103, 104], "B": [100, 101, 102, 103, 104]})
        self.assertEqual(result["status"], "FORWARD_OBSERVING")
        self.assertTrue(result["forward"]["economic_continuity_verified"])
        self.assertIsNone(result["source_health"]["unresolved_forward_gap"])
        self.assertEqual(len(result["forward"]["observations"]), 4)
        self.assertEqual(result["forward"]["latest_close"], "2026-09-15")


    def test_implicit_target_reset_turnover_uses_exact_scored_returns(self):
        dates = pd.to_datetime(["2026-09-10", "2026-09-11"])
        daily = pd.DataFrame({"A": [0.10, 0.0], "B": [-0.10, 0.0]}, index=dates)
        weights = {"A": 0.5, "B": 0.5}
        states = {"2026-09": {"p249_core": weights, "p249_plus_p266": weights}}
        rows = [
            {"date": "2026-09-10", "holding_month": "2026-09",
             "p249_core_gross": 0.0, "p249_plus_p266_gross": 0.0},
            {"date": "2026-09-11", "holding_month": "2026-09",
             "p249_core_gross": 0.0, "p249_plus_p266_gross": 0.0},
        ]
        audit = observer._implicit_target_reset_turnover_audit(rows, daily, states)
        self.assertEqual(audit["status"], "DIAGNOSTIC_ONLY_UNCHARGED_IMPLICIT_RESETS")
        self.assertEqual(audit["transitions"], 1)
        for arm in ("p249_core", "p249_plus_p266"):
            self.assertAlmostEqual(audit["arms"][arm]["intramonth_one_way_turnover"], 0.05)
            self.assertEqual(audit["arms"][arm]["intramonth_reset_count"], 1)
            self.assertEqual(audit["arms"][arm]["month_boundary_count"], 0)
        self.assertTrue(audit["not_actual_trades_or_funded_monthly_hold"])

    def test_month_boundary_turnover_is_separate_from_intramonth_reset(self):
        dates = pd.to_datetime(["2026-09-30", "2026-10-01"])
        daily = pd.DataFrame({"A": [0.0, 0.0], "B": [0.0, 0.0]}, index=dates)
        states = {
            "2026-09": {"p249_core": {"A": 0.5, "B": 0.5},
                        "p249_plus_p266": {"A": 0.5, "B": 0.5}},
            "2026-10": {"p249_core": {"A": 0.75, "B": 0.25},
                        "p249_plus_p266": {"A": 0.75, "B": 0.25}},
        }
        rows = [
            {"date": "2026-09-30", "holding_month": "2026-09",
             "p249_core_gross": 0.0, "p249_plus_p266_gross": 0.0},
            {"date": "2026-10-01", "holding_month": "2026-10",
             "p249_core_gross": 0.0, "p249_plus_p266_gross": 0.0},
        ]
        audit = observer._implicit_target_reset_turnover_audit(rows, daily, states)
        for arm in ("p249_core", "p249_plus_p266"):
            self.assertAlmostEqual(audit["arms"][arm]["month_boundary_one_way_turnover"], 0.25)
            self.assertEqual(audit["arms"][arm]["month_boundary_count"], 1)
            self.assertEqual(audit["arms"][arm]["intramonth_reset_count"], 0)

    def test_turnover_audit_rejects_nonchronological_and_unfunded_source(self):
        dates = pd.to_datetime(["2026-09-10", "2026-09-11"])
        daily = pd.DataFrame({"A": [0.0, 0.0], "B": [0.0, 0.0]}, index=dates)
        weights = {"A": 0.5, "B": 0.5}
        states = {"2026-09": {"p249_core": weights, "p249_plus_p266": weights}}
        row = {"date": "2026-09-10", "holding_month": "2026-09",
               "p249_core_gross": 0.0, "p249_plus_p266_gross": 0.0}
        with self.assertRaisesRegex(ValueError, "NONCHRONOLOGICAL"):
            observer._implicit_target_reset_turnover_audit([row, row], daily, states)
        invalid = dict(row, p249_core_gross=-1.0)
        following = dict(row, date="2026-09-11")
        with self.assertRaisesRegex(ValueError, "INVALID_WEALTH"):
            observer._implicit_target_reset_turnover_audit([invalid, following], daily, states)


if __name__ == "__main__":
    unittest.main()
