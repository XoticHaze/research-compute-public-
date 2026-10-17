from __future__ import annotations

"""No-data, no-parameter-change acceptance gates for the frozen P249 tournament."""

import unittest

import numpy as np
import pandas as pd

from research import p249_orthogonal_sleeve_tournament_r1 as m


class FrozenP249TournamentTests(unittest.TestCase):
    def test_one_common_capital_rule_for_all_sleeves(self):
        self.assertEqual(m.CANDIDATE_WEIGHT, 0.25)
        self.assertEqual(m.CORE_WEIGHT, 0.75)
        self.assertEqual(m.CANDIDATE_WEIGHT + m.CORE_WEIGHT, 1.0)
        self.assertEqual(m.CASH, "BIL")
        self.assertEqual(m.CANDIDATES, ["P266", "JAAA", "SRLN", "KMLM"])
        self.assertEqual(m.END, "2026-09-01")
        self.assertGreater(m.MIX_REBALANCE_COST, 0)
        self.assertGreater(m.ENDPOINT_COST, 0)

    def test_pure_core_sleeve_rebalance_and_matched_bil_control(self):
        dates = pd.date_range("2022-01-31", periods=24, freq="ME")
        core = pd.Series([0.01] * 24, index=dates)
        sleeve = pd.Series([0.03] * 24, index=dates)
        cash = pd.Series([0.002] * 24, index=dates)
        row = m.frame(core, sleeve, cash, start="2022-01-01")
        self.assertEqual(row["months"], 24)
        self.assertGreater(row["matched_capital_excess_cagr_pp"], 0)
        self.assertGreater(row["core_cagr_delta_pp"], 0)
        self.assertIsNotNone(row["challenger"]["max_drawdown"])
        self.assertLessEqual(max(m.mix_net(core, sleeve)), 0.015)
        self.assertTrue(np.isfinite(m.mix_net(core, cash)).all())

    def test_exact_negative_and_uncovered_candidates_not_ranked(self):
        template = {
            "persistence_passed": False,
            "windows": {"2021+": {
                "matched_capital_excess_cagr_pp": 200,
                "core_cagr_delta_pp": 200,
                "sharpe_delta_vs_core": 200,
                "maxdd_improvement_vs_core_pp": 200,
                "downside_excess_to_core_corr": 0,
            }},
        }
        bad = {n: template for n in m.CANDIDATES}
        self.assertEqual(m.rank_candidates(bad), [])

    def test_common_downside_control_does_not_infer_promotion(self):
        dates = pd.date_range("2022-01-31", periods=24, freq="ME")
        core = pd.Series([-0.01] * 12 + [0.02] * 12, index=dates)
        sleeve = pd.Series([0.001] * 24, index=dates)
        cash = pd.Series([0.002] * 24, index=dates)
        row = m.frame(core, sleeve, cash, start="2022-01-01")
        self.assertEqual(row["downside_months"], 12)
        self.assertEqual(row["sleeve_positive_when_core_negative_fraction"], 1.0)
        self.assertLess(row["matched_capital_excess_cagr_pp"], 0)


if __name__ == "__main__":
    unittest.main()
