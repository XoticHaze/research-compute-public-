from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.ibkr_auth_boundary_v1 import classify
from scripts.ibkr_login_window_guard_v1 import classify_window


class AuthBoundaryTests(unittest.TestCase):
    def test_raw_controller_twofa_phase_is_not_a_real_challenge(self):
        result = classify("[state: TWO_FA]\nPost-login inspection", "Authenticating")
        self.assertTrue(result["controller_internal_twofa_phase"])
        self.assertFalse(result["second_factor_challenge_observed"])
        self.assertEqual(result["stage"], "controller_internal_twofa_phase_only")

    def test_exact_ibkey_wait_signal_is_authoritative(self):
        result = classify(
            "IB Key 2FA dialog detected\nWaiting for IB Key mobile approval — approve on your phone",
            "ns_auth_start",
        )
        self.assertTrue(result["second_factor_challenge_observed"])
        self.assertTrue(result["ibkey_mobile_approval_wait_signal"])
        self.assertEqual(result["stage"], "ibkey_mobile_approval_wait")

    def test_ccp_lockout_wins_over_internal_twofa_phase(self):
        result = classify(
            "[state: TWO_FA]\nmaintenance\nCCP lockout authentication backoff",
            "Authenticating",
        )
        self.assertFalse(result["second_factor_challenge_observed"])
        self.assertEqual(result["stage"], "ccp_auth_lockout_backoff")

    def test_device_selection_is_concrete_challenge(self):
        result = classify("Select a device for second factor authentication", "")
        self.assertTrue(result["device_selection_observed"])
        self.assertTrue(result["second_factor_challenge_observed"])


class ResetWindowTests(unittest.TestCase):
    def test_inside_reset_guard_is_blocked(self):
        # 2026-09-16 05:35Z == 01:35 EDT.
        result = classify_window(datetime(2026, 9, 16, 5, 35, tzinfo=timezone.utc))
        self.assertFalse(result["cold_login_allowed"])
        self.assertEqual(result["reason"], "north_america_daily_reset_guard")

    def test_after_guard_margin_is_allowed(self):
        # 2026-09-16 05:51Z == 01:51 EDT.
        result = classify_window(datetime(2026, 9, 16, 5, 51, tzinfo=timezone.utc))
        self.assertTrue(result["cold_login_allowed"])
        self.assertEqual(result["reason"], "outside_reset_guard")

    def test_before_guard_start_is_allowed(self):
        # 2026-09-16 04:09Z == 00:09 EDT.
        result = classify_window(datetime(2026, 9, 16, 4, 9, tzinfo=timezone.utc))
        self.assertTrue(result["cold_login_allowed"])


if __name__ == "__main__":
    unittest.main()
