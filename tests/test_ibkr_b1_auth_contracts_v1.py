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
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "controller_internal_twofa_phase_only")

    def test_exact_ibkey_wait_signal_is_authoritative(self):
        result = classify(
            "IB Key 2FA dialog detected\nWaiting for IB Key mobile approval — approve on your phone",
            "Authenticating\nReceived NS_AUTH_START",
        )
        self.assertTrue(result["second_factor_challenge_observed"])
        self.assertTrue(result["ibkey_mobile_approval_wait_signal"])
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "ibkey_mobile_approval_wait")

    def test_concrete_ccp_lockout_is_terminal_prechallenge_blocker(self):
        result = classify(
            "[state: TWO_FA]\nCCP authentication lockout; retry later",
            "Authenticating",
        )
        self.assertFalse(result["second_factor_challenge_observed"])
        self.assertTrue(result["ccp_lockout_observed"])
        self.assertTrue(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "ccp_auth_lockout_backoff")

    def test_authorization_disconnect_before_ns_auth_is_terminal_but_not_called_bad_credentials(self):
        result = classify(
            "[state: TWO_FA]",
            "Connecting ndc1.ibllc.com:4001 (SSL)\nAuthenticating\n"
            "Disconnecting ndc1.ibllc.com:4001 (SSL) "
            "[disconnectDetails=DisconnectDetails[reason=DISCONNECT_AUTHORIZATION_FAILED]]",
        )
        self.assertTrue(result["authorization_rejected_before_ns_auth"])
        self.assertFalse(result["credential_rejection_observed"])
        self.assertFalse(result["ns_auth_start_observed"])
        self.assertTrue(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "authorization_rejected_before_ns_auth")
        self.assertIn("DISCONNECT_AUTHORIZATION_FAILED", "\n".join(result["launcher_auth_transcript"]))

    def test_exact_ccp_timeout_before_ns_auth_is_terminal(self):
        result = classify(
            "[state: TWO_FA]",
            "Connecting ndc1.ibllc.com:4001 (SSL)\nAuthenticating\nAuthTimeoutMonitor-CCP: Timeout!",
        )
        self.assertTrue(result["ccp_timeout_observed"])
        self.assertTrue(result["ccp_silent_timeout_before_ns_auth"])
        self.assertTrue(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "ccp_silent_timeout_before_ns_auth")
        self.assertEqual(result["launcher_connected_host"], "ndc1.ibllc.com")

    def test_pre_ns_auth_stall_after_sixty_seconds_is_terminal(self):
        result = classify(
            "[state: TWO_FA]\n2FA wait t+60s: still waiting",
            "Connecting ndc1.ibllc.com:4001 (SSL)\nAuthenticating",
        )
        self.assertTrue(result["pre_ns_auth_stall_observed"])
        self.assertFalse(result["ns_auth_start_observed"])
        self.assertTrue(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "authentication_stalled_before_ns_auth")

    def test_ccp_timeout_after_ns_auth_is_not_silent_pre_auth_timeout(self):
        result = classify(
            "[state: TWO_FA]",
            "Authenticating\nReceived NS_AUTH_START\nAuthTimeoutMonitor-CCP: Timeout!",
        )
        self.assertTrue(result["ccp_timeout_observed"])
        self.assertTrue(result["ns_auth_start_observed"])
        self.assertFalse(result["ccp_silent_timeout_before_ns_auth"])
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "ns_auth_before_second_factor")

    def test_unrelated_maintenance_word_does_not_claim_active_reset(self):
        result = classify(
            "CCP service initialized\n[state: TWO_FA]",
            "Authenticating with server\nmaintenance metadata loaded",
        )
        self.assertFalse(result["ccp_lockout_observed"])
        self.assertFalse(result["maintenance_observed"])
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "controller_internal_twofa_phase_only")

    def test_active_maintenance_delay_is_distinct_but_not_terminal(self):
        result = classify("cold start inside IBKR maintenance window; maintenance recovery delay", "Authenticating")
        self.assertTrue(result["maintenance_observed"])
        self.assertFalse(result["ccp_lockout_observed"])
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "active_maintenance_or_reset_guard")

    def test_ssl_server_handshake_failure_is_terminal(self):
        result = classify(
            "[state: TWO_FA]",
            "Connecting ndc1.ibllc.com:4000\nSSLHandshakeException: Remote host terminated the handshake",
        )
        self.assertTrue(result["ssl_handshake_failure_observed"])
        self.assertTrue(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "ssl_or_regional_server_handshake_failure")

    def test_evidence_excerpt_and_launcher_transcript_are_redacted(self):
        result = classify(
            "username=alice@example.com password=hunter2 CCP lockout authentication retry later",
            "Connecting cdc1.ibllc.com:4001\naccount DU123456 PostAuthenticate",
        )
        excerpt = "\n".join(result["evidence_excerpt"])
        transcript = "\n".join(result["launcher_auth_transcript"])
        self.assertIn("username=<redacted>", excerpt)
        self.assertIn("password=<redacted>", excerpt)
        self.assertIn("<redacted-account>", transcript)
        self.assertNotIn("alice@example.com", excerpt)
        self.assertNotIn("hunter2", excerpt)
        self.assertNotIn("DU123456", transcript)
        self.assertEqual(result["launcher_connected_host"], "cdc1.ibllc.com")

    def test_device_selection_is_concrete_challenge(self):
        result = classify("Select a device for second factor authentication", "")
        self.assertTrue(result["device_selection_observed"])
        self.assertTrue(result["second_factor_challenge_observed"])
        self.assertFalse(result["terminal_prechallenge_blocker"])

    def test_warm_api_ready_does_not_require_second_factor(self):
        result = classify("API port open — session preserved", "")
        self.assertTrue(result["api_ready_observed"])
        self.assertFalse(result["second_factor_challenge_observed"])
        self.assertFalse(result["terminal_prechallenge_blocker"])
        self.assertEqual(result["stage"], "api_ready")


class ResetWindowTests(unittest.TestCase):
    def test_inside_reset_guard_is_blocked(self):
        result = classify_window(datetime(2026, 9, 16, 5, 35, tzinfo=timezone.utc))
        self.assertFalse(result["cold_login_allowed"])
        self.assertEqual(result["reason"], "north_america_daily_reset_guard")

    def test_after_guard_margin_is_allowed(self):
        result = classify_window(datetime(2026, 9, 16, 5, 51, tzinfo=timezone.utc))
        self.assertTrue(result["cold_login_allowed"])
        self.assertEqual(result["reason"], "outside_reset_guard")

    def test_before_guard_start_is_allowed(self):
        result = classify_window(datetime(2026, 9, 16, 4, 9, tzinfo=timezone.utc))
        self.assertTrue(result["cold_login_allowed"])


if __name__ == "__main__":
    unittest.main()
