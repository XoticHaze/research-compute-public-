"""Focused synthetic source-safe validation for the CC Cloudflare credential readback."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import ccpi_cloudflare_cc_token_scope_probe_v1 as probe


class CCCloudflareScopeProbeTests(unittest.TestCase):
    def test_scope_reads_are_get_only_and_never_emit_token(self):
        calls = []

        def fake_open(request, timeout=0):
            calls.append((request.full_url, request.get_method(), timeout))
            self.assertEqual(request.get_method(), "GET")
            self.assertIn("Bearer opaque-secret", request.get_header("Authorization"))
            return type("Reply", (), {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: False,
                "status": 403,
            })()

        with mock.patch.object(probe, "urlopen", side_effect=fake_open):
            status = probe.summarize("opaque-secret", probe.ORIGINAL_ACCOUNT)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(method == "GET" for _, method, _ in calls))
        self.assertNotIn("opaque-secret", json.dumps(status))
        self.assertEqual(status["neutral_scripts_list_http"], 403)

    def test_unconfigured_credentials_issue_no_calls(self):
        with mock.patch.object(probe, "urlopen") as opener:
            result = probe.summarize("", probe.ORIGINAL_ACCOUNT)
        opener.assert_not_called()
        self.assertFalse(result["configured"])
        self.assertEqual(result["verify_http"], "NOT_CONFIGURED")

    def test_account_mismatch_rejected_before_api(self):
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.dict(os.environ, {
                 "CC_CF_ORIGINAL_ACCOUNT": probe.NEUTRAL_ACCOUNT,
                 "CCPI_SCOPE_PROBE_RECEIPT": str(Path(temp) / "receipt.json"),
                 "CC_CF_R2_TOKEN": "opaque-secret",
             }), mock.patch.object(probe, "urlopen") as opener:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(
                SystemExit, "IDENTITY_UNVERIFIED"):
                probe.main()
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
