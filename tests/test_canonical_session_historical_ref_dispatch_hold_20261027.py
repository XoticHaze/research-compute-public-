"""Regression: historical refs cannot manually dispatch the legacy canonical session.

Source-only check. Never dispatch a workflow, decrypt a capsule, or materialize P01.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/mmibkr-canonical-research-session-bau-r1.yml"


class CanonicalSessionHistoricalRefHoldTest(unittest.TestCase):
    def test_default_branch_has_no_manual_dispatch_trigger(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        header = source.split("\npermissions:", 1)[0]
        self.assertRegex(header, r"(?m)^  push:$")
        self.assertRegex(header, r"(?m)^      - main$")
        self.assertNotRegex(header, r"(?m)^  workflow_dispatch\s*:")
        # A historical ref can contain a pre-hold workflow with reversible
        # session_zlib_b64. Never permit default-branch manual dispatch of it.
        self.assertIn("historical branch refs retain pre-hold", header)

    def test_current_push_trigger_still_fails_closed_before_checkout(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        first_step = source.split("\n    steps:\n", 1)[1].split("\n      - uses:", 1)[0]
        self.assertIn("CONFIDENTIAL_SESSION_ADMISSION=FAIL_CLOSED", first_step)
        self.assertIn("CONFIDENTIAL_SESSION_REASON=two_sided_private_transport_not_admitted", first_step)
        self.assertIn("exit 78", first_step)
        self.assertLess(source.index("Fail closed before private source"),
                        source.index("actions/checkout@"))


if __name__ == "__main__":
    unittest.main()
