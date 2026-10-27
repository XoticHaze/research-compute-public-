"""Synthetic source-only regression for P558/JAAA after-cost forward comparisons.

No live data, confidential input, placement, portfolio mutation or new model.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

# Permit isolated offline tests without installing the market-data client.
try:
    import yfinance  # noqa: F401
except ImportError:
    sys.modules["yfinance"] = types.SimpleNamespace(download=lambda *a, **k: None)


class FundedDiversifierComparatorTests(unittest.TestCase):
    def _run(self, module_name: str, candidate: str, missing_cash_session: bool = False):
        module = importlib.import_module(module_name)
        dates = pd.to_datetime(["2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15"])
        close = pd.DataFrame(
            {candidate: [100.0, 101.0, 102.0, 103.0],
             "BIL": [100.0, 100.1, float("nan") if missing_cash_session else 100.2, 100.3]},
            index=dates,
        )
        prices = pd.concat({"Close": close}, axis=1)
        core = {
            "forward": {"observations": [
                {"date": "2026-09-11", "p249_plus_p266_net": 0.010},
                {"date": "2026-09-14", "p249_plus_p266_net": -0.005},
                {"date": "2026-09-15", "p249_plus_p266_net": 0.004},
            ]},
            "current_state": {"p249_plus_p266": {"SOXX": 0.5, "QQQ": 0.5}},
        }
        with tempfile.TemporaryDirectory() as root:
            inp, out = Path(root) / "core.json", Path(root) / "out.json"
            inp.write_text(json.dumps(core))
            with mock.patch.object(module.runpy, "run_path", return_value={}), \
                 mock.patch.object(module, "LEGACY_ARTIFACT", inp), \
                 mock.patch.object(module, "OUTPUT", out), \
                 mock.patch.object(module.yf, "download", return_value=prices):
                if missing_cash_session:
                    with self.assertRaisesRegex(RuntimeError, "FORWARD_MATCHED_SESSION_SET_MISMATCH"):
                        module.main()
                    return
                module.main()
            return json.loads(out.read_text())["forward"]

    def test_p558_and_senior_clo_use_identical_funded_nav_cost_basis(self):
        for module, candidate in (
            ("research.forward_p558_current_core_shadow_r1", "KMLM"),
            ("research.forward_senior_clo_current_core_shadow_r1", "JAAA"),
        ):
            with self.subTest(module=module):
                fwd = self._run(module, candidate)
                challenger = fwd["challenger_if_flattened_now"]["cumulative_return"]
                matched = fwd["matched_control_if_flattened_now"]["cumulative_return"]
                incumbent = fwd["incumbent"]["cumulative_return"]
                self.assertAlmostEqual(fwd["challenger_minus_matched_cumulative"], challenger - matched)
                self.assertAlmostEqual(fwd["challenger_minus_incumbent_cumulative"], challenger - incumbent)
                self.assertEqual(fwd["comparison_cost_basis"]["challenger_minus_matched_cumulative"],
                                 "BOTH_NET_IF_FLATTENED_NOW")
                self.assertEqual(fwd["comparison_cost_basis"]["challenger_minus_incumbent_cumulative"],
                                 "CHALLENGER_NET_IF_FLATTENED_NOW_MINUS_UNCHANGED_INCUMBENT_NET")
                # The previous source compounded pre-exit daily returns for
                # excess while publishing a post-exit absolute challenger.
                old_pre_exit = 1.0
                core_wealth = 1.0
                for row in fwd["challenger_observations"]:
                    old_pre_exit *= 1.0 + row["net_return"]
                    core_wealth *= 1.0 + row["core_return"]
                self.assertGreater(abs(fwd["challenger_minus_incumbent_cumulative"] -
                                       (old_pre_exit - core_wealth)), 0.002)

    def test_missing_matched_cash_session_fails_closed(self):
        for module, candidate in (
            ("research.forward_p558_current_core_shadow_r1", "KMLM"),
            ("research.forward_senior_clo_current_core_shadow_r1", "JAAA"),
        ):
            with self.subTest(module=module):
                self._run(module, candidate, missing_cash_session=True)


if __name__ == "__main__":
    unittest.main()
