"""Brokerless and secretless tests of the Cloudflare Worker deployment token route."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import mmibkr_operator_console_deploy_token_route_v1 as sut


class _Response:
    status = 200
    def __init__(self, success=True):
        self._body = json.dumps({"success": success, "result": {"subdomain": "example"}}).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self._body


class DeployTokenRouteTests(unittest.TestCase):
    def test_scoped_token_preferred_when_both_authorized(self):
        calls = []
        def check(token, account):
            calls.append((token, account))
            return True
        self.assertEqual(sut.select_route("account", "scoped", "legacy", check), "scoped_r2")
        self.assertEqual(calls, [("scoped", "account")])

    def test_existing_legacy_token_used_only_when_r2_lacks_account_subdomain(self):
        calls = []
        def check(token, account):
            calls.append(token)
            return token == "legacy"
        self.assertEqual(sut.select_route("account", "scoped", "legacy", check), "legacy_existing")
        self.assertEqual(calls, ["scoped", "legacy"])

    def test_missing_or_denied_tokens_fail_before_wrangler(self):
        for scoped, legacy in [("", ""), ("scoped", ""), ("scoped", "legacy")]:
            with self.subTest(scoped=bool(scoped), legacy=bool(legacy)):
                with self.assertRaisesRegex(ValueError, "SUBDOMAIN_AUTH_REQUIRED"):
                    sut.select_route("account", scoped, legacy, lambda *_: False)
        with self.assertRaisesRegex(ValueError, "ACCOUNT_ID_REQUIRED"):
            sut.select_route("", "scoped", "legacy")

    def test_requires_account_subdomain_and_exact_worker_settings(self):
        seen = []
        def fake_open(request, timeout=0):
            seen.append(request.full_url)
            return _Response()
        with patch.object(sut, "urlopen", side_effect=fake_open):
            self.assertTrue(sut.worker_token_ready("synthetic-token", "synthetic-account"))
        self.assertEqual([x.rsplit("/", 2)[-2:] for x in seen][0][-1], "subdomain")
        self.assertTrue(seen[1].endswith("/workers/scripts/mmibkr-operator-console/settings"))
        self.assertEqual(len(seen), 2)
        with patch.object(sut, "urlopen", side_effect=PermissionError("sensitive!")):
            self.assertFalse(sut.worker_token_ready("synthetic-token", "synthetic-account"))

    def test_main_emits_only_route_and_never_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            env = {
                "GITHUB_OUTPUT": str(output),
                "CLOUDFLARE_ACCOUNT_ID": "synthetic-account",
                "CLOUDFLARE_DEPLOY_TOKEN_R2": "highly-secret-token",
                "CLOUDFLARE_LEGACY_WORKERS_TOKEN": "another-secret",
            }
            with patch.dict(os.environ, env, clear=True), \
                 patch.object(sut, "worker_token_ready", side_effect=[False, True]), \
                 patch("sys.stdout", new_callable=io.StringIO) as logged:
                self.assertEqual(sut.main(), 0)
                message = logged.getvalue()
            self.assertEqual(output.read_text(), "route=legacy_existing\n")
            self.assertNotIn("highly-secret-token", message)
            self.assertNotIn("another-secret", message)
            self.assertNotIn("synthetic-account", message)
            self.assertIn("WORKERS_SUBDOMAIN_PREFLIGHT=PASS", message)


if __name__ == "__main__":
    unittest.main()
