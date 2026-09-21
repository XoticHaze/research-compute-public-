from __future__ import annotations

from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cloudflare" / "operator-console" / "src" / "index.js"
WRANGLER = ROOT / "cloudflare" / "operator-console" / "wrangler.jsonc"


class OperatorConsoleWorkerContractTests(unittest.TestCase):
    def test_browser_surface_requires_cloudflare_access_jwt(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("cf-access-jwt-assertion", text)
        self.assertIn("ACCESS_TEAM_DOMAIN", text)
        self.assertIn("ACCESS_AUD", text)
        self.assertIn("/cdn-cgi/access/certs", text)
        self.assertIn("access_denied", text)
        self.assertIn("verifyAccess(request, env)", text)

    def test_publisher_is_github_oidc_bound_to_cloud_owner_workflows(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("mmibkr-operator-console", text)
        self.assertIn("token.actions.githubusercontent.com", text)
        self.assertIn("XoticHaze/research-compute-public-", text)
        self.assertIn("XoticHaze/mm-ibkr-runtime", text)
        self.assertIn("mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main", text)
        self.assertIn("runner_environment", text)
        self.assertIn("repository_visibility", text)
        self.assertIn("x-mmibkr-caller-run-id", text)

    def test_snapshot_fails_closed_on_privacy_and_authority_flags(self):
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "mmibkr.cloud_operator_snapshot.v1",
            "private_operator_state",
            "account_identifiers_included",
            "credentials_included",
            "tokens_included",
            "private_source_included",
            "execution_authority_included",
            "presentation_projection_only",
            "strategy_authority",
            "execution_policy_authority",
            "sizing_authority",
            "broker_mutation_authority",
            "live_execution_allowed",
        ):
            self.assertIn(marker, text)
        self.assertIn("snapshot_privacy_contract_rejected", text)
        self.assertIn("snapshot_authority_contract_rejected", text)

    def test_static_assets_run_through_worker_first(self):
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        assets = config["assets"]
        self.assertTrue(assets["run_worker_first"])
        self.assertEqual(assets["binding"], "ASSETS")
        self.assertEqual(assets["not_found_handling"], "single-page-application")
        self.assertEqual(config["name"], "mmibkr-operator-console")

    def test_private_snapshot_state_is_durable_object_backed(self):
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        bindings = config["durable_objects"]["bindings"]
        self.assertEqual(
            bindings,
            [{"name": "OPERATOR_STATE", "class_name": "OperatorState"}],
        )
        self.assertEqual(config["exports"]["OperatorState"]["storage"], "sqlite")
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("this.ctx.storage.put('latest'", text)
        self.assertIn("this.ctx.storage.get('latest')", text)

    def test_worker_does_not_embed_broker_or_private_source_credentials(self):
        text = SOURCE.read_text(encoding="utf-8")
        forbidden = (
            "IBKR_PAPER_USERNAME",
            "IBKR_PAPER_PASSWORD",
            "MMIBKR_PRIVATE_SOURCE_TOKEN",
            "IBKR_REMOTE_SOURCE_TOKEN",
            "TWS_PASSWORD",
        )
        for marker in forbidden:
            self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
