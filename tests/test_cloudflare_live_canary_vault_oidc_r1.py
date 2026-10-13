from pathlib import Path
import unittest

SOURCE = Path("cloudflare/fleet-authority/src/source_exchange.js").read_text(encoding="utf-8")
CANARY = Path(".github/workflows/mmibkr-cloudflare-live-canary-r1.yml").read_text(encoding="utf-8")
EXPECTED = "9a190fe66665c8f673d227a41c4544889a2cf2cb"


class CloudCanaryOidcScope(unittest.TestCase):
    def test_exact_main_workflow_identity(self):
        self.assertIn("const CLOUD_CANARY_DEPLOY_IDENTITY = {", SOURCE)
        self.assertIn("XoticHaze/research-compute-public-/.github/workflows/mmibkr-cloudflare-live-canary-r1.yml@refs/heads/main", SOURCE)
        self.assertIn("const CLOUD_CANARY_DEPLOY_APPROVED_SOURCE =", SOURCE)
        self.assertIn(EXPECTED, SOURCE)
        self.assertIn("PRIVATE_SOURCE_SHA: " + EXPECTED, CANARY)

    def test_only_exact_unwrap_endpoint_on_push(self):
        self.assertIn("const cloudCanaryUnwrapPathAllowed = (", SOURCE)
        self.assertIn("pathname === '/v1/source-vault/unwrap'\n      && claims.event_name === 'push'", SOURCE)
        self.assertIn("matchedCloudCanaryDeploy && cloudCanaryUnwrapPathAllowed", SOURCE)
        self.assertNotIn("matchedCloudCanaryDeploy && privateArchivePathAllowed", SOURCE)

    def test_source_pin_enforced_after_oidc_identity_forwarded(self):
        self.assertIn("matchesIdentity(requestIdentity, CLOUD_CANARY_DEPLOY_IDENTITY)", SOURCE)
        self.assertIn("sourceSha !== CLOUD_CANARY_DEPLOY_APPROVED_SOURCE", SOURCE)
        self.assertIn("throw new Error('cloud_canary_exact_source_sha_rejected')", SOURCE)

    def test_no_broker_vault_seal_auth_granted(self):
        auth = Path("cloudflare/fleet-authority/src/index.js").read_text(encoding="utf-8")
        self.assertNotIn("CLOUD_CANARY_DEPLOY_IDENTITY", auth)
        self.assertNotIn("CLOUD_CANARY_DEPLOY_APPROVED_SOURCE", auth)
        self.assertNotIn("matchedCloudCanaryDeploy", auth)

    def test_cloud_workflow_declares_no_broker_and_no_orders(self):
        self.assertIn('if n.get("no_broker") is not True or n.get("no_orders") is not True:', CANARY)
        self.assertIn('assert config["vars"]["CANARY_START_ENABLED"] == "0"', CANARY)
        self.assertIn('assert config["vars"]["LIVE_ORDER_EXECUTION_ENABLED"] == "0"', CANARY)
        self.assertIn("CLOUDFLARE_LIVE_CANARY_DEPLOY_TOKEN", CANARY)


if __name__ == "__main__":
    unittest.main()
