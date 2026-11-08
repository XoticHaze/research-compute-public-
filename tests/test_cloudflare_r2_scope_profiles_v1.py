"""Offline Cloudflare R2 token scope profiles: no network, secrets or deployment."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloudflare_r2_scope_preflight as sut


class R2ScopeProfilesContract(unittest.TestCase):
    def invoke(self, profile, console_status):
        def fake_request(token, method, url):
            self.assertEqual(token, "synthetic-token")
            self.assertEqual(method, "GET")
            worker = url.rsplit("/", 2)[-2]
            if worker == "fleet-authority":
                return 200, {"success": True}
            if worker == "mmibkr-operator-console":
                return console_status, {"success": console_status == 200}
            return 403, {"success": False}

        with tempfile.TemporaryDirectory() as temp:
            old = os.getcwd()
            try:
                os.chdir(temp)
                env = {
                    "CLOUDFLARE_ACCOUNT_ID": "synthetic-account",
                    "CLOUDFLARE_API_TOKEN": "synthetic-token",
                }
                if profile is not None:
                    env["CLOUDFLARE_R2_SCOPE_PROFILE"] = profile
                with patch.dict(os.environ, env, clear=True), patch.object(sut, "request", side_effect=fake_request), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        result = sut.main()
                        failure = None
                    except SystemExit as exc:
                        result = None
                        failure = str(exc)
                receipt_path = Path("rendezvous/receipts/research-cloudflare-r2-scope-preflight.json")
                receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
                return result, failure, receipt
            finally:
                os.chdir(old)

    def test_default_dual_preserves_existing_scope(self):
        result, failure, receipt = self.invoke(None, 200)
        self.assertEqual(result, 0)
        self.assertIsNone(failure)
        self.assertEqual(receipt["scope_profile"], "dual")
        self.assertEqual(receipt["expected_allow"], ["fleet-authority", "mmibkr-operator-console"])
        self.assertTrue(receipt["pass"])

    def test_transition_supports_present_or_removed_console_scope(self):
        for http_status in (200, 403, 404):
            with self.subTest(http_status=http_status):
                result, failure, receipt = self.invoke("fleet_transition", http_status)
                self.assertEqual(result, 0)
                self.assertIsNone(failure)
                self.assertEqual(receipt["expected_allow"], ["fleet-authority"])
                self.assertEqual(receipt["worker_settings_http"]["mmibkr-operator-console"], http_status)
                self.assertTrue(receipt["pass"])

    def test_strict_rejects_retained_console_access(self):
        result, failure, receipt = self.invoke("fleet_strict", 200)
        self.assertIsNone(result)
        self.assertIn("forbidden_worker_reachable:mmibkr-operator-console", failure)
        self.assertFalse(receipt["pass"])

    def test_strict_accepts_console_scope_removed(self):
        result, failure, receipt = self.invoke("fleet_strict", 403)
        self.assertEqual(result, 0)
        self.assertIsNone(failure)
        self.assertIn("mmibkr-operator-console", receipt["expected_deny"])
        self.assertTrue(receipt["pass"])

    def test_unknown_profile_fails_without_probing_or_deployment(self):
        result, failure, receipt = self.invoke("disable_checks", 403)
        self.assertIsNone(result)
        self.assertEqual(failure, "R2 scope profile invalid")
        self.assertIsNone(receipt)


if __name__ == "__main__":
    unittest.main()
