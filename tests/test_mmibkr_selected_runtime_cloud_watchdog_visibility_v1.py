from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml"
)


class SelectedRuntimeCloudWatchdogVisibilityTests(unittest.TestCase):
    def test_no_checkpoint_is_reported_as_no_owner_not_successful_bot(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        guard = workflow.split("if not checkpoint_key or not checkpoint_sha:", 1)[1]
        no_checkpoint, dispatch = guard.split("payload=json.dumps({", 1)
        self.assertIn("MMIBKR_CLOUD_WATCHDOG=no_current_source_checkpoint", no_checkpoint)
        self.assertIn("no owner dispatched", no_checkpoint)
        self.assertIn("::warning title=MM-IBKR selected-runtime owner not dispatched", no_checkpoint)
        self.assertIn("GITHUB_STEP_SUMMARY", no_checkpoint)
        self.assertIn("raise SystemExit(0)", no_checkpoint)
        self.assertNotIn("dispatch=Request(", no_checkpoint)
        self.assertIn("dispatch=Request(", dispatch)

    def test_inline_watchdog_python_is_syntactically_valid(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        owner_section = workflow.split(
            "      - name: Ensure one selected-runtime cloud owner exists", 1
        )[1]
        inline = owner_section.split("          python - <<'PY'\n", 1)[1]
        inline = inline.split("\n          PY", 1)[0]
        code = "\n".join(
            line[10:] if line.startswith("          ") else line
            for line in inline.splitlines()
        )
        compile(code, "<MM-IBKR watchdog inline owner>", "exec")

    def test_warning_does_not_change_source_or_mutation_policy(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "canonical_source='cd431670749a4c48d87c07b164ef1e4219bef7ca'",
            workflow,
        )
        self.assertIn(
            "'source_ref':'cd431670749a4c48d87c07b164ef1e4219bef7ca'",
            workflow,
        )
        self.assertNotIn("ENABLE_LIVE_TRADING=1", workflow)
        self.assertIn("Broker mutations: none", workflow)


if __name__ == "__main__":
    unittest.main()
