from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cloudflare" / "fleet-authority" / "src" / "source_exchange.js"
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-exact-private-validation-r1.yml"
TARGET = "468a4d5ca3d235c5ae89547f2d906103ebf9bcf8"


class ExactPrivateValidationContractTests(unittest.TestCase):
    def test_fleet_identity_is_exact_and_sha_scoped(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("EXACT_PRIVATE_VALIDATION_IDENTITY", text)
        self.assertIn("mmibkr-exact-private-validation-r1.yml@refs/heads/main", text)
        self.assertIn("EXACT_PRIVATE_VALIDATION_SOURCE", text)
        self.assertIn(TARGET, text)
        self.assertIn("matchedExactPrivateValidation && privateArchivePathAllowed", text)

    def test_workflow_runs_canonical_private_hostless_suite_without_live_authority(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"PRIVATE_SOURCE_SHA: {TARGET}", text)
        self.assertIn("tests.test_strategy_registry_position_state_forwarding_v1", text)
        self.assertIn("tests.test_snapshot_ib_adapter_position_state_v1", text)
        self.assertIn("tests.test_selected_runtime_cloud_natural_evaluator_v1", text)
        self.assertIn("MMIBKR_PRIVATE_PLAINTEXT_EMITTED=0", text)
        self.assertIn("MMIBKR_LIVE_EXECUTION_ALLOWED=0", text)


if __name__ == "__main__":
    unittest.main()
