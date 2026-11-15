"""Narrow fail-closed checks for reuse of existing Fleet Cloudflare credentials."""
import unittest
from scripts.fleet_authority_deploy_token_route_v1 import select_route, WORKER


class FleetAuthorityDeployTokenSelectionTests(unittest.TestCase):
    def test_prefers_scoped_when_fully_capable(self):
        calls = []
        def probe(token, account):
            calls.append((token, account))
            return token == "scoped"
        self.assertEqual(select_route("account", "scoped", "legacy", probe), "scoped_r2")
        self.assertEqual(calls, [("scoped", "account")])

    def test_legacy_fallback_when_scoped_lacks_subdomain(self):
        def probe(token, account):
            return token == "legacy"
        self.assertEqual(select_route("account", "scoped", "legacy", probe), "legacy_existing")

    def test_no_capable_token_fails_before_upload(self):
        with self.assertRaisesRegex(ValueError, "SUBDOMAIN_AUTH_REQUIRED"):
            select_route("account", "scoped", "legacy", lambda token, account: False)

    def test_no_account_rejected_and_worker_exact(self):
        with self.assertRaisesRegex(ValueError, "ACCOUNT_ID_REQUIRED"):
            select_route("", "scoped", "legacy")
        self.assertEqual(WORKER, "fleet-authority")


if __name__ == "__main__":
    unittest.main()
