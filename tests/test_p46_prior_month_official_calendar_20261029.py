"""P46 source admission: a resampled month-end is not a complete source month."""
from __future__ import annotations

import unittest

import exchange_calendars as xc
import pandas as pd

from research.p46_forward_observer_r2 import U, _official_prior_feature_month_health

OBSERVED = pd.Timestamp("2026-11-02T12:00:00Z")


def october_sessions() -> pd.DatetimeIndex:
    return xc.get_calendar("XNYS").sessions_in_range(
        "2026-10-01", "2026-10-31"
    ).tz_localize(None)


def panel(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({symbol: [100.0 + i for i in range(len(index))]
                         for symbol in U}, index=index)


class P46OfficialPriorMonthSourceTests(unittest.TestCase):
    def test_complete_october_allows_prospective_source(self):
        health = _official_prior_feature_month_health(panel(october_sessions()), OBSERVED)
        self.assertEqual(health["required_feature_month"], "2026-10")
        self.assertEqual(health["expected_official_sessions"], 22)
        self.assertEqual(health["observed_common_sessions"], 22)
        self.assertEqual(health["last_official_session"], "2026-10-30")
        self.assertTrue(health["source_complete"])

    def test_shared_missing_last_official_session_rejected(self):
        incomplete = october_sessions().drop(pd.Timestamp("2026-10-30"))
        with self.assertRaisesRegex(RuntimeError, "P46_PRIOR_MONTH_SOURCE_INCOMPLETE"):
            _official_prior_feature_month_health(panel(incomplete), OBSERVED)

    def test_shared_missing_interior_official_session_rejected(self):
        incomplete = october_sessions().drop(pd.Timestamp("2026-10-15"))
        with self.assertRaisesRegex(RuntimeError, "P46_PRIOR_MONTH_SOURCE_INCOMPLETE"):
            _official_prior_feature_month_health(panel(incomplete), OBSERVED)

    def test_stale_september_cannot_masquerade_as_october(self):
        sept = xc.get_calendar("XNYS").sessions_in_range(
            "2026-09-01", "2026-09-30"
        ).tz_localize(None)
        with self.assertRaisesRegex(RuntimeError, "P46_PRIOR_MONTH_SOURCE_INCOMPLETE"):
            _official_prior_feature_month_health(panel(sept), OBSERVED)

    def test_nonexchange_weekend_rejected(self):
        extra = october_sessions().union(pd.DatetimeIndex(["2026-10-31"]))
        with self.assertRaisesRegex(RuntimeError, "P46_PRIOR_MONTH_SOURCE_INCOMPLETE"):
            _official_prior_feature_month_health(panel(extra), OBSERVED)


if __name__ == "__main__":
    unittest.main()
