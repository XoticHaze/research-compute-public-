"""No stale neutral broker editor secret identity or pre-submission audit expectations."""
from __future__ import annotations
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class NeutralMaintainerBindingSourceTests(unittest.TestCase):
    def test_single_worker_editor_store_binding_uses_submitted_name(self):
        cfg = json.loads((ROOT / "cloudflare/reference-release-maintainer/wrangler.jsonc").read_text())
        self.assertEqual(cfg["name"], "reference-release-maintainer-v1")
        self.assertEqual(cfg["secrets_store_secrets"], [{
            "binding": "BROKER_EDITOR_TOKEN",
            "store_id": "3bdb660e7b8d4de6a1688f922f3991f7",
            "secret_name": "BROKER_EDITOR_TOKEN",
        }])
        self.assertNotIn("REFERENCE_RELEASE_BROKER_EDITOR_TOKEN", json.dumps(cfg))

    def test_readonly_version_audit_requires_maintainer_binding_not_authority_binding(self):
        source = (ROOT / "scripts/run_shared_compute_neutral_active_version_audit_macos.sh").read_text()
        self.assertIn("BROKER_EDITOR_ABSENT_ON_AUTHORITY", source)
        self.assertIn("BROKER_EDITOR_SECRETS_STORE_BOUND_ON_MAINTAINER", source)
        self.assertIn("effective_binding_readback_then_independent_signer_seal", source)
        self.assertNotIn("BROKER_EDITOR_ABSENT_'+role", source)
        self.assertNotIn("isolated_secret_provisioning", source)

if __name__ == "__main__":
    unittest.main()
