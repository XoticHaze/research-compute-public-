from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research import shared_ridge_matched_risk_shadow_r1 as shadow

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research/current/forward_prospective_cohort_ledger_r1.json"
SCORE = ROOT / "research/current/forward_market_scoreboard_r1.json"


class SharedRidgeMatchedRiskShadowTests(unittest.TestCase):
    def setUp(self):
        self.ledger = json.loads(LEDGER.read_text())
        self.scoreboard = json.loads(SCORE.read_text())
        cohort, result, variants = shadow.frozen_inputs(self.ledger, self.scoreboard)
        self.assertEqual(len(variants["frozen_inverse_vol"]), 13)
        dates = pd.bdate_range(shadow.ENTRY, shadow.EXIT)
        self.assertEqual(len(dates), 21)
        names = sorted(cohort["symbols"])
        # Synthetic daily path, exact terminal gross returns from frozen recorded
        # outcomes; science cannot use this synthetic shape as real risk evidence.
        price = pd.DataFrame(index=dates)
        for s in names:
            end = 1 + result["ticker_observations"][s]["gross_return_bps"] / 10000.0
            price[s] = 100 * (1 + np.linspace(0, end - 1, len(dates)))
        smh_end = 1 + result["benchmarks"]["smh_buy_and_hold_return_bps"] / 10000.0
        price["SMH"] = 100 * (1 + np.linspace(0, smh_end - 1, len(dates)))
        self.prices = price

    def test_public_frozen_evidence_lineage_and_equal_matched_costs(self):
        before = copy.deepcopy(self.ledger)
        out = shadow.compute(self.ledger, self.scoreboard, self.prices)
        self.assertEqual(before, self.ledger)
        self.assertEqual(out["scientific_disposition"], "HISTORICAL_MATCHED_RISK_DIAGNOSTIC_ONLY")
        self.assertEqual(out["observed_session_intervals"], 20)
        self.assertEqual(set(out["results"]), {
            "frozen_inverse_vol", "equal_weight", "forecast_proportional", "forecast_div_vol"
        })
        r = out["results"]
        self.assertAlmostEqual(r["frozen_inverse_vol"]["net_terminal_bps"], 895.5707, delta=1.0)
        self.assertGreater(r["forecast_proportional"]["net_terminal_bps"],
                           r["frozen_inverse_vol"]["net_terminal_bps"])
        self.assertTrue(all(abs(sum(row["weights_within_cohort"].values()) - 1) < 1e-7
                            for row in r.values()))
        self.assertTrue(all(row["max_close_to_close_drawdown"] <= 0 for row in r.values()))
        self.assertFalse(out["policy"]["broker_action"])
        self.assertFalse(out["policy"]["alternative_weight_promotion"])

    def test_does_not_make_outcome_or_volatility_model_authority(self):
        out = shadow.compute(self.ledger, self.scoreboard, self.prices)
        self.assertEqual(out["results"]["forecast_proportional"]["evidence_stage"],
                         "RETROSPECTIVE_ONLY_NO_FORWARD_CREDIT")
        self.assertLess(out["results"]["forecast_proportional"]["concentration_top_five"], 1)
        self.assertEqual(out["baseline"], "frozen_inverse_vol")

    def test_baseline_and_identity_drift_fail_closed(self):
        bad = copy.deepcopy(self.ledger)
        bad["cohorts"] = [c for c in bad["cohorts"] if c.get("cohort_id") != shadow.COHORT]
        with self.assertRaises(ValueError):
            shadow.compute(bad, self.scoreboard, self.prices)
        bad = copy.deepcopy(self.scoreboard)
        lane = next(x for x in bad["lanes"] if x["program_id"] == shadow.PROGRAM)
        lane["paper_action"]["ticker_book"]["cohort_target_weights_nav"]["AMD"] *= 2
        with self.assertRaises(ValueError):
            shadow.compute(self.ledger, bad, self.prices)

    def test_missing_daily_path_or_benchmark_drift_fail_closed(self):
        with self.assertRaises(ValueError):
            shadow.compute(self.ledger, self.scoreboard,
                           self.prices.drop(self.prices.index[5]))
        bad = self.prices.copy()
        bad.loc[bad.index[-1], "SMH"] *= 1.03
        with self.assertRaises(ValueError):
            shadow.compute(self.ledger, self.scoreboard, bad)


if __name__ == "__main__":
    unittest.main()
