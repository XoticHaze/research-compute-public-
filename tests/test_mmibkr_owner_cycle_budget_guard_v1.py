from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class OwnerCycleBudgetGuardTests(unittest.TestCase):
    def test_owner_request_cannot_be_shorter_than_private_daemon_cycle_budget(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("if session_seconds < 1200 or session_seconds > 18000:", text)
        self.assertIn(
            "session_seconds must be 1200..18000 so the private daemon can enter at least one cycle",
            text,
        )
        self.assertNotIn("session_seconds must be 900..18000", text)

    def test_default_owner_session_remains_well_above_guard(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("default: '18000'", text)
        self.assertIn("payload.get('session_seconds') or 18000", text)


if __name__ == "__main__":
    unittest.main()
