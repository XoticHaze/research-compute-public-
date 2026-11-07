"""Focused synthetic source-only checks for the frozen P249/P266 fee shadow.

These do not authenticate provider rights, real fills, external placement or
the original published forward observation.
"""
from __future__ import annotations

import math
import unittest

import pandas as pd

from research.p279_p249_p266_forward_shadow_observer_r1 import (
    _monthly_hold_heterogeneous_fee_shadow,
)


class MonthlyHeterogeneousFeeShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"date": "2026-09-10", "holding_month": "2026-09", "cost_detail": {}},
            {"date": "2026-09-11", "holding_month": "2026-09", "cost_detail": None},
            {"date": "2026-10-01", "holding_month": "2026-10", "cost_detail": {}},
        ]
        self.daily = pd.DataFrame(
            {"AVUV": [0.0, 0.01, 0.0], "SOXX": [0.0, -0.02, 0.03]},
            index=pd.to_datetime(["2026-09-10", "2026-09-11", "2026-10-01"]),
        )
        self.months = {
            "2026-09": {
                "p249_core": {"AVUV": 0.5, "SOXX": 0.5},
                "p249_plus_p266": {"AVUV": 0.25, "SOXX": 0.75},
            },
            "2026-10": {
                "p249_core": {"AVUV": 0.25, "SOXX": 0.75},
                "p249_plus_p266": {"AVUV": 0.5, "SOXX": 0.5},
            },
        }

    def test_exact_initial_fee_and_month_boundary_cash_identity(self) -> None:
        result = _monthly_hold_heterogeneous_fee_shadow(self.rows, self.daily, self.months)
        extension = _monthly_hold_heterogeneous_fee_shadow(
            self.rows, self.daily, self.months, small_value_rebalance_fee_bp=10.0
        )
        self.assertEqual(result["status"], "SOURCE_ONLY_HETEROGENEOUS_MONTHLY_HOLD_FEE_SHADOW")
        self.assertTrue(result["small_value_entry_only_frozen_convention_preserved"])
        self.assertFalse(extension["small_value_entry_only_frozen_convention_preserved"])
        self.assertTrue(extension["small_value_rebalance_fee_is_explicit_extension_of_frozen_entry_rate"])
        self.assertTrue(result["no_legacy_month_fee_double_charge"])
        for arm, initial_fee in [("p249_core", 0.003), ("p249_plus_p266", 0.004)]:
            data = result["arms"][arm]
            self.assertEqual(len(data["fee_events"]), 2)
            self.assertEqual(len(data["daily_nav"]), 3)
            first, second = data["fee_events"]
            extension_events = extension["arms"][arm]["fee_events"]
            self.assertAlmostEqual(first["fee_nav"], extension_events[0]["fee_nav"], places=12)
            self.assertGreater(extension_events[1]["fee_nav"], second["fee_nav"])
            self.assertTrue(first["initial_entry"])
            self.assertFalse(second["initial_entry"])
            self.assertAlmostEqual(first["postfee_nav"], 1.0 / (1.0 + initial_fee), places=12)
            self.assertAlmostEqual(first["postfee_nav"] + first["fee_nav"], 1.0, places=12)
            self.assertAlmostEqual(second["postfee_nav"] + second["fee_nav"], second["pretrade_nav"], places=12)
            self.assertAlmostEqual(
                second["gross_buy_notional_nav"] - second["gross_sell_notional_nav"] + second["fee_nav"],
                0.0, places=12,
            )
            self.assertTrue(math.isfinite(data["terminal_nav"]))
            self.assertGreater(data["terminal_nav"], 0.0)
        core = result["arms"]["p249_core"]["terminal_nav"]
        combo = result["arms"]["p249_plus_p266"]["terminal_nav"]
        self.assertAlmostEqual(result["matched_relative_wealth_bp"], 10000.0 * (combo / core - 1.0), places=10)

    def test_missing_monthly_cost_boundary_fails_closed(self) -> None:
        rows = [dict(self.rows[0], cost_detail=None)]
        with self.assertRaisesRegex(ValueError, "MISSING_MONTH_BOUNDARY"):
            _monthly_hold_heterogeneous_fee_shadow(rows, self.daily, self.months)


if __name__ == "__main__":
    unittest.main()
