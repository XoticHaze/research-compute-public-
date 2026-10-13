from __future__ import annotations

import json
import unittest
from pathlib import Path
from scripts.fleet_authority_r2_deploy_receipt_v1 import make_receipt


class FleetR2ReceiptTruthTests(unittest.TestCase):
    def test_wranger_failure_never_claims_deploy_success(self):
        node = make_receipt(wrangler_outcome="failure", credential_selection="scoped_r2")
        self.assertFalse(node["deploy_pass"])
        self.assertFalse(node["fresh_deploy_confirmed"])
        self.assertTrue(node["deployed_source_verified"])
        self.assertTrue(node["control_plane_pass"])
        self.assertTrue(node["health_pass"])
        self.assertFalse(node["r2_confidential_execution_proven"])

    def test_fresh_wranger_success_is_provable_separate_from_host_r2(self):
        node = make_receipt(wrangler_outcome="success", credential_selection="scoped_r2")
        self.assertTrue(node["deploy_pass"])
        self.assertTrue(node["fresh_deploy_confirmed"])
        self.assertFalse(node["r2_confidential_execution_proven"])

    def test_invalid_outcome_fails_closed(self):
        for value in ("", "unknown", "skipped", "cancelled"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_receipt(wrangler_outcome=value, credential_selection="scoped_r2")
        with self.assertRaises(ValueError):
            make_receipt(wrangler_outcome="success", credential_selection="unscoped")

    def test_receipt_has_no_secret_or_arbitrary_error_fields(self):
        for outcome in ("success", "failure"):
            rendered = json.dumps(make_receipt(wrangler_outcome=outcome, credential_selection="scoped_r2"))
            self.assertNotIn("CLOUDFLARE_DEPLOY_TOKEN", rendered)
            self.assertNotIn("Authorization", rendered)
            self.assertNotIn("source_sha", rendered)
            self.assertNotIn("error_details", rendered)

    def test_active_workflow_uses_truthful_receipt_builder(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/fleet-authority-deploy-r2.yml").read_text()
        self.assertIn("from scripts.fleet_authority_r2_deploy_receipt_v1 import make_receipt", workflow)
        self.assertIn("wrangler_outcome=os.environ['FLEET_AUTHORITY_WRANGLER_OUTCOME']", workflow)
        self.assertIn("tests.test_fleet_authority_r2_deploy_receipt_v1", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertNotIn('"deploy_pass": True', workflow)


if __name__ == "__main__":
    unittest.main()
