"""The shared signed harness must target the isolated neutral broker account."""
from __future__ import annotations
import ast
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
