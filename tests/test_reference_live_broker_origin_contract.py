"""The shared signed harness must target the isolated neutral broker account."""
from __future__ import annotations
import ast
import json
from pathlib import Path
import unittest

NEUTRAL = (
    "https://reference-release-broker-v1."
    "shared-compute-neutral-authorization.workers.dev/v1/release"
)

class NeutralBrokerOriginTests(unittest.TestCase):
    def test_reusable_workflow_pins_neutral_source_immutably(self):
        path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "secure-compute-harness-v1.yml"
        workflow = path.read_text()
        self.assertIn("ref: 75adddd9f041981fd5db642c1d6d73e9b62f2070", workflow)
        self.assertNotIn("ref: 16ec0a2a94b058fa9b120b707de92463e64b068b", workflow)

    def test_broker_policy_and_caller_pin_same_immutable_workflow(self):
        root = Path(__file__).resolve().parents[1]
        sha = "e8a4574e6c8c7f65e40bb662192b9adb2d8adfdf"
        workflow_ref = "XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@" + sha
        caller = (root / ".github" / "workflows" / "reference-live-release-proof.yml").read_text()
        config = json.loads((root / "cloudflare" / "reference-release-broker" / "wrangler.jsonc").read_text())
        self.assertIn("uses: " + workflow_ref, caller)
        self.assertEqual(config["vars"]["ALLOWED_JOB_WORKFLOW_REF"], workflow_ref)
        self.assertEqual(config["vars"]["ALLOWED_JOB_WORKFLOW_SHA"], sha)
        self.assertNotIn("477b76085c06f77fee72b57771225a66545aa43f", caller)
        self.assertNotEqual(config["vars"]["ALLOWED_JOB_WORKFLOW_SHA"], "477b76085c06f77fee72b57771225a66545aa43f")

    def test_live_reference_harness_uses_neutral_broker_only(self):
        source = (Path(__file__).resolve().parents[1] /
                  "scripts" / "live_reference_harness_v1.py").read_text()
        module = ast.parse(source)
        assignments = [
            item.value.value for item in module.body
            if isinstance(item, ast.Assign)
            and any(isinstance(name, ast.Name) and name.id == "BROKER_URL"
                    for name in item.targets)
            and isinstance(item.value, ast.Constant)
        ]
        self.assertEqual(assignments, [NEUTRAL])
        self.assertNotIn("slenderiq.workers.dev", source)

if __name__ == "__main__":
    unittest.main()
