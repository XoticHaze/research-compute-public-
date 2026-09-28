from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-canonical-research-session-bau-r1.yml"


class CanonicalSessionPushFireWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_push_fire_path_and_manual_dispatch_coexist(self):
        text = self.text
        self.assertIn("push:", text)
        self.assertIn("branches:", text)
        self.assertIn("- main", text)
        self.assertIn("rendezvous/fire/mmibkr-canonical-research-session-bau-r1.json", text)
        self.assertIn("workflow_dispatch:", text)

    def test_push_event_requires_typed_embedded_session_and_exact_source_ref(self):
        text = self.text
        self.assertIn("if event=='push':", text)
        self.assertIn("mmibkr.canonical_session_fire.v1", text)
        self.assertIn("canonical session fire requires session object", text)
        self.assertIn("mmibkr.canonical_session.v1", text)
        self.assertIn("source_ref must be exact 40-hex SHA", text)
        self.assertIn("expected job SHA256 invalid", text)

    def test_push_and_dispatch_join_same_canonical_execution_path(self):
        text = self.text
        self.assertEqual(text.count("Execute finite canonical session"), 1)
        self.assertIn("scripts/mmibkr_canonical_session_runner_v1.py", text)
        self.assertIn("--source-root \"$MMIBKR_CANONICAL_SOURCE_ROOT\"", text)
        self.assertIn("--input-root \"$RUNNER_TEMP/input-root\"", text)
        self.assertIn("mmibkr.canonical_session_receipt.v1", text)

    def test_research_only_authority_is_preserved_in_terminal_receipt(self):
        text = self.text
        for assertion in (
            "'strategy_spec_write':False",
            "'runtime_activation':False",
            "'broker_submit':False",
            "'broker_cancel':False",
            "'broker_flatten':False",
            "'promotion_mutation':False",
            "'live_trading':False",
        ):
            self.assertIn(assertion, text)


if __name__ == "__main__":
    unittest.main()
