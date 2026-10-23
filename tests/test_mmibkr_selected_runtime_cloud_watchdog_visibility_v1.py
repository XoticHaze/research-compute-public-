from __future__ import annotations

import re
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
        # A workflow pin can advance independently of this observability PR.
        # Require one exact 40-hex owner pin and the SAME dispatch source,
        # rather than freezing a retired commit in the visibility test.
        source_pin = re.search(r"canonical_source='([0-9a-f]{40})'", workflow)
        dispatch_pin = re.search(r"'source_ref':'([0-9a-f]{40})'", workflow)
        self.assertIsNotNone(source_pin)
        self.assertIsNotNone(dispatch_pin)
        self.assertEqual(source_pin.group(1), dispatch_pin.group(1))
        self.assertNotIn("ENABLE_LIVE_TRADING=1", workflow)
        self.assertIn("Broker mutations: none", workflow)



class SelectedRuntimeCloudWatchdogCheckpointOriginTests(unittest.TestCase):
    """Synthetic origin guards; no source capsule, broker or owner dispatched."""

    SOURCE = "b" * 40
    PUBLIC = "a" * 40

    def sample(self):
        run = {
            "id": 123456, "status": "completed", "conclusion": "success",
            "event": "workflow_dispatch", "head_branch": "main",
            "head_sha": self.PUBLIC,
        }
        receipt = {
            "schema": "mmibkr.selected_runtime_cloud_session_receipt.v2",
            "run_id": "123456", "private_head": self.SOURCE,
            "public_head": self.PUBLIC,
            "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
            "ok": True, "session_accepted": True,
            "checkpoint_handoff_ready": True,
            "checkpoint_cache_saved": True,
            "checkpoint_cache_key": "synthetic-cache-key",
            "live_execution_allowed": False, "credentials_included": False,
            "account_state_included": False, "positions_included": False,
            "orders_included": False,
        }
        return run, receipt

    def test_exact_successful_owner_metadata_is_eligible_for_later_checkpoint_checks(self):
        from scripts.mmibkr_selected_runtime_cloud_watchdog_cooldown_v1 import (
            checkpoint_receipt_origin_admitted,
        )
        run, receipt = self.sample()
        self.assertTrue(checkpoint_receipt_origin_admitted(run, receipt, self.SOURCE))
        # This predicate alone never proves cache existence, signed issuer,
        # broker account history, sole ownership or successor continuity.

    def test_failed_or_unmatched_github_run_never_reuses_saved_checkpoint(self):
        from scripts.mmibkr_selected_runtime_cloud_watchdog_cooldown_v1 import (
            checkpoint_receipt_origin_admitted,
        )
        for field, value in (
            ("conclusion", "failure"), ("conclusion", "cancelled"),
            ("status", "in_progress"), ("event", "pull_request"),
            ("head_branch", "other"), ("head_sha", "c" * 40),
            ("id", 123457),
        ):
            with self.subTest(field=field, value=value):
                run, receipt = self.sample()
                run[field] = value
                self.assertFalse(
                    checkpoint_receipt_origin_admitted(run, receipt, self.SOURCE)
                )

    def test_unaccepted_or_cross_run_receipt_cannot_qualify(self):
        from scripts.mmibkr_selected_runtime_cloud_watchdog_cooldown_v1 import (
            checkpoint_receipt_origin_admitted,
        )
        for field, value in (
            ("ok", False), ("ok", 1), ("session_accepted", "true"),
            ("checkpoint_handoff_ready", False),
            ("run_id", "123457"), ("private_head", "c" * 40),
            ("public_head", "d" * 40),
            ("schema", "other"), ("source_transport", "caller_supplied"),
            ("live_execution_allowed", True), ("credentials_included", None),
            ("account_state_included", 0), ("positions_included", "false"),
            ("orders_included", True),
        ):
            with self.subTest(field=field, value=value):
                run, receipt = self.sample()
                receipt[field] = value
                self.assertFalse(
                    checkpoint_receipt_origin_admitted(run, receipt, self.SOURCE)
                )
        run, receipt = self.sample()
        self.assertFalse(checkpoint_receipt_origin_admitted(run, receipt, "not-a-sha"))

    def test_inline_workflow_enforces_origin_before_cache_candidate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("checkpoint_receipt_origin_admitted,", workflow)
        self.assertIn("checkpoint_receipt_origin_admitted(run, receipt, canonical_source)", workflow)
        self.assertIn("receipt=receipt_for(run)", workflow)
        self.assertLess(
            workflow.index("checkpoint_receipt_origin_admitted(run, receipt, canonical_source)"),
            workflow.index("saved_key=str(receipt.get('checkpoint_cache_key')"),
        )


if __name__ == "__main__":
    unittest.main()
