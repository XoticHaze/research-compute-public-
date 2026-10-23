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

    def test_complete_held_closes_continue_scoring(self):
        result = self._run({"A": [100, 101, 102, 103, 104], "B": [100, 101, 102, 103, 104]})
        self.assertEqual(result["status"], "FORWARD_OBSERVING")
        self.assertTrue(result["forward"]["economic_continuity_verified"])
        self.assertIsNone(result["source_health"]["unresolved_forward_gap"])
        self.assertEqual(len(result["forward"]["observations"]), 4)
        self.assertEqual(result["forward"]["latest_close"], "2026-09-15")


if __name__ == "__main__":
    unittest.main()
