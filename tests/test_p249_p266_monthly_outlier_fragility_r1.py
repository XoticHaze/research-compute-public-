from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research import p249_p266_monthly_outlier_fragility_r1 as d


class P249P266OutlierFragilityTests(unittest.TestCase):
    def setUp(self):
        ix = pd.date_range("2021-01-31", periods=68, freq="ME")
        self.core = pd.Series([0.012] * 68, index=ix)
        p266 = [0.013] * 68
        p266[0] = 0.35
        p266[1] = 0.25
        self.p266 = pd.Series(p266, index=ix)
        self.cash = pd.Series([0.002] * 68, index=ix)

    def test_exact_common_months_and_monotone_removed_sets(self):
        r = d.diagnose(self.core, self.p266, self.cash)
        self.assertEqual(r["schema"], d.SCHEMA)
        self.assertEqual([x["removed_best_increment_months"] for x in r["cohorts"]], [0, 1, 3, 5])
        previous = set()
        for row in r["cohorts"]:
            removed = set(row["removed_months"])
            self.assertTrue(previous.issubset(removed))
            self.assertEqual(row["remaining_months"], 68 - len(removed))
            previous = removed
        self.assertEqual(r["cohorts"][1]["removed_months"], ["2021-01-31"])
        self.assertFalse(r["allocation_authority"])
        self.assertFalse(r["live_trading_change"])

    def test_malformed_or_unmatched_history_fails_closed(self):
        with self.assertRaises(ValueError):
            d.diagnose(self.core.iloc[:20], self.p266, self.cash)
        missing = self.cash.drop(self.cash.index[:25])
        with self.assertRaises(ValueError):
            d.diagnose(self.core, self.p266, missing)

    def test_negative_increment_is_not_posthoc_fixed_by_month_omission(self):
        p266 = self.core - 0.015
        r = d.diagnose(self.core, p266, self.cash)
        self.assertLess(r["cohorts"][0]["incremental_vs_core_cagr_pp"], 0)
        self.assertLess(r["cohorts"][-1]["incremental_vs_core_cagr_pp"], 0)


if __name__ == "__main__":
    unittest.main()
