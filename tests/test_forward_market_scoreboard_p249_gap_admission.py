from __future__ import annotations

"""One changed-consumer boundary: canonical P249 source admission governs scoreboard economics."""

import copy
import unittest

from research.forward_market_scoreboard_r1 import _p249
from research.forward_p249_p266_shadow_r1 import current_publication_admitted


def _valid_observation():
    return {
        "schema": "research.forward_p249_p266_shadow_r1",
        "parent": "P249/P266/P278",
        "workload_id": "FORWARD_P249_P266_SHADOW_R1",
        "status": "FORWARD_OBSERVING",
        "source_health": {
            "unresolved_forward_gap": None,
            "latest_scored_common_session": "2026-10-22",
        },
        "current_state": {
            "p249_core": {"SOXX": 1.0},
            "p266": {"XBI": 1.0},
            "p249_plus_p266": {"SOXX": 0.8, "XBI": 0.2},
        },
        "forward": {
            "economic_continuity_verified": True,
            "latest_close": "2026-10-22",
            "observations": [{"date": "2026-10-22", "satellite_increment_net": 0.002}],
            "p249_core_net": {"days": 1, "cumulative_return": 0.01, "annualized_vol": 0.12},
            "p249_plus_p266_net": {"days": 1, "cumulative_return": 0.012, "annualized_vol": 0.14},
            "satellite_increment_cumulative": 0.002,
        },
    }


class ScoreboardP249SourceAdmissionTests(unittest.TestCase):
    def test_admitted_observation_keeps_economics_and_frozen_weights(self):
        payload = _valid_observation()
        self.assertTrue(current_publication_admitted(payload))
        lane = _p249(payload)
        self.assertTrue(lane["economic_current_admitted"])
        self.assertEqual(lane["forward_days"], 1)
        self.assertEqual(lane["scorecard"]["p249_core_net_cumulative_bps"], 100.0)
        self.assertEqual(lane["scorecard"]["p249_plus_p266_net_cumulative_bps"], 120.0)
        self.assertEqual(lane["paper_action"]["SOXX"], 0.8)

    def test_gap_blocks_all_partial_economic_scorecard_fields(self):
        payload = copy.deepcopy(_valid_observation())
        payload["status"] = "SOURCE_GAP_UNRESOLVED"
        payload["source_health"]["unresolved_forward_gap"] = {"missing_close": ["XBI"]}
        payload["forward"]["economic_continuity_verified"] = False
        self.assertFalse(current_publication_admitted(payload))
        lane = _p249(payload)
        self.assertFalse(lane["economic_current_admitted"])
        self.assertEqual(lane["validation_grade"], "SOURCE_GAP_UNRESOLVED")
        self.assertIsNone(lane["forward_days"])
        self.assertTrue(all(value is None for value in lane["scorecard"].values()))
        self.assertEqual(lane["paper_action_authority"], "prior_frozen_context_only_not_new_economic_current")
        self.assertEqual(lane["source_health"]["unresolved_forward_gap"]["missing_close"], ["XBI"])

    def test_invalid_current_identity_cannot_become_economic_current(self):
        payload = _valid_observation()
        payload["workload_id"] = "OTHER"
        lane = _p249(payload)
        self.assertFalse(lane["economic_current_admitted"])
        self.assertEqual(lane["validation_grade"], "ECONOMIC_SOURCE_NOT_ADMITTED")
        self.assertTrue(all(value is None for value in lane["scorecard"].values()))


if __name__ == "__main__":
    unittest.main()
