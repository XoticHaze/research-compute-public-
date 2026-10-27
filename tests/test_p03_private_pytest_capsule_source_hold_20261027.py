"""Source-only regression for the existing P03 executable-capsule hold.

This does not execute/decrypt private payloads or authenticate a producer.
It preserves the fail-closed job boundary until an independent trusted issuer,
exact source digest and private return are admitted by their owners.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/p03-private-pytest-ephemeral-rendezvous.yml"
CONSUMER = ROOT / "scripts/p03_private_pytest_ephemeral_consumer_v1.py"


class P03PrivatePytestCapsuleSourceHoldTest(unittest.TestCase):
    def test_untrusted_executable_capsule_job_is_inert(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  pull_request:", workflow)
        self.assertIn("  contents: write", workflow)
        marker = "\njobs:\n  consume:\n"
        self.assertEqual(workflow.count(marker), 1)
        before_runner = workflow.split(marker, 1)[1].split("\n    runs-on:", 1)[0]
        self.assertIn("    if: ${{ false }}", before_runner)

    def test_hold_covers_capsule_supplied_executable_python(self):
        consumer = CONSUMER.read_text(encoding="utf-8")
        self.assertIn('env["sender_public_b64"]', consumer)
        self.assertIn('manifest["source_sha256"]', consumer)
        self.assertIn('manifest["test_sha256"]', consumer)
        self.assertIn("tf.extractall(root)", consumer)
        self.assertIn("subprocess.run(", consumer)

    def test_position_duration_executable_capsule_job_is_inert(self):
        workflow = (ROOT / ".github/workflows/p03-private-binding-ephemeral-rendezvous.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:", workflow)
        self.assertIn("  contents: write", workflow)
        marker = "\\njobs:\\n  consume:\\n"
        self.assertEqual(workflow.count(marker), 1)
        before_runner = workflow.split(marker, 1)[1].split("\\n    runs-on:", 1)[0]
        self.assertIn("    if: ${{ false }}", before_runner)
        consumer = (ROOT / "scripts/p03_private_binding_contract_consumer_v1.py").read_text(encoding="utf-8")
        self.assertIn('env["sender_public_b64"]', consumer)
        self.assertIn('manifest["operator_source_sha256"]', consumer)
        self.assertIn('manifest["operator_test_sha256"]', consumer)
        self.assertIn("tf.extractall(root)", consumer)
        self.assertIn("subprocess.run(", consumer)


if __name__ == "__main__":
    unittest.main()
