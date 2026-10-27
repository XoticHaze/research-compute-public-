"""Brokerless exact reset-window discriminator for the existing read-only Gateway pool.

No IBKR client, credentials, Gateway process, or live order route is exercised.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
import unittest
from pathlib import Path
from textwrap import dedent

WORKFLOW = Path(".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml")


class GatewayResetWindowObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        start = cls.source.index("          pool_reset_window_outage() {\n")
        end = cls.source.index("          while :; do\n", start)
        cls.function = dedent(cls.source[start:end])
        assert cls.function.count("pool_reset_window_outage() {") == 1

    def _eligible(self, utc_epoch: int, *, used: int = 0) -> bool:
        script = "\n".join((
            "set -euo pipefail",
            f"outage_since={utc_epoch}",
            f"reset_window_grace_used={used}",
            self.function,
            "pool_reset_window_outage",
        ))
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_real_observed_friday_reset_outage_eligible(self):
        # 2026-10-23 04:57:50 UTC = Friday 00:57:50 America/New_York.
        self.assertTrue(self._eligible(1792731470))

    def test_exact_reset_window_edges(self):
        # Friday EDT: 00:14 false, 00:15 true, 01:45 true, 01:46 false.
        self.assertFalse(self._eligible(1792728840))
        self.assertTrue(self._eligible(1792728900))
        self.assertTrue(self._eligible(1792734300))
        self.assertFalse(self._eligible(1792734360))

    def test_saturday_maintenance_window_and_ordinary_outage(self):
        # Official IBKR Saturday maintenance 00:00-02:00 ET is a separate
        # bounded read-only observation window from Sunday-Friday reset.
        cases = (
            ("2026-10-24T00:00:00-04:00", True),
            ("2026-10-24T00:57:50-04:00", True),
            ("2026-10-24T01:59:00-04:00", True),
            ("2026-10-24T02:00:00-04:00", False),
            ("2026-10-23T23:59:00-04:00", False),
        )
        for eastern, expected in cases:
            with self.subTest(eastern=eastern):
                self.assertEqual(
                    self._eligible(int(datetime.fromisoformat(eastern).timestamp())),
                    expected,
                )
        self.assertFalse(self._eligible(1792745870))  # Friday 04:57 ET
        self.assertFalse(self._eligible(0))  # No observed outage
        self.assertFalse(self._eligible(1792817870, used=1))  # No repeat grace

    def test_only_readonly_observation_extended_and_bounded(self):
        source = self.source
        start = source.index("      - name: Hold one authenticated read-only Gateway")
        end = source.index("      - name: Confirm no-order admission", start)
        pool = source[start:end]
        self.assertIn("inputs.admission_only && inputs.warm_handoff_mode == 'gateway_pool_5h'", pool)
        self.assertIn('docker exec mmibkr-live-gateway /bin/sh -lc \'test "$READ_ONLY_API" = yes\'', pool)
        self.assertIn("MMIBKR_GATEWAY_POOL_RESET_WINDOW_READONLY_OBSERVATION_STARTED=1", pool)
        self.assertIn("observation_budget=600", pool)
        self.assertIn('[ "$outage_eastern_weekday" -eq 6 ]', pool)
        self.assertIn("observation_budget=720", pool)
        self.assertIn('[ "$now" -ge "$((end + observation_budget))" ]', pool)
        self.assertIn('[ "$now" -ge "$((outage_since + observation_budget))" ]', pool)
        self.assertNotIn("placeOrder(", pool)
        self.assertNotIn("cancelOrder(", pool)


if __name__ == "__main__":
    unittest.main()
