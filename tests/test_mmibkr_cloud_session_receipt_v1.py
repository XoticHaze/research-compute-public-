from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class CloudSessionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_receipt_carries_durable_checkpoint_acceptance(self):
        for marker in (
            "id: restore_checkpoint",
            "restored=true",
            "restored=false",
            "id: checkpoint_saved",
            "MMIBKR_RECEIPT_CHECKPOINT_RESTORED",
            "MMIBKR_RECEIPT_CHECKPOINT_CACHE_READY",
            "MMIBKR_RECEIPT_CHECKPOINT_CACHE_SAVED",
            "'public_head': os.environ.get('GITHUB_SHA')",
            "receipt['checkpoint_restored']",
            "receipt['checkpoint_restored_sha256']",
            "receipt['checkpoint_restored_cache_key']",
            "receipt['checkpoint_cache_ready']",
            "receipt['checkpoint_cache_saved']",
            "receipt['checkpoint_cache_sha256']",
            "receipt['checkpoint_cache_key']",
        ):
            self.assertIn(marker, self.text)

    def test_receipt_carries_sanitized_operator_publish_acceptance(self):
        for marker in (
            "id: operator_snapshot",
            "publish_status",
            "runtime_count",
            "positions_count",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_STREAM_COUNT",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_STREAM_ATTEMPTS",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_PUBLISH",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_RUNTIME_COUNT",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_POSITIONS_COUNT",
            "MMIBKR_RECEIPT_OPERATOR_SNAPSHOT_DURABLE_READBACK",
            "receipt['operator_snapshot_stream_publish_count']",
            "receipt['operator_snapshot_stream_attempt_count']",
            "receipt['operator_snapshot_publish']",
            "'durable_readback_verified':",
            "'account_identifiers_included': False if publish_accepted else None",
            "'credentials_included': False if publish_accepted else None",
            "'tokens_included': False if publish_accepted else None",
            "'private_source_included': False if publish_accepted else None",
            "'execution_authority_included': False if publish_accepted else None",
            "'broker_mutation_authority': False if publish_accepted else None",
            "'live_execution_allowed': False if publish_accepted else None",
        ):
            self.assertIn(marker, self.text)

    def test_v2_receipt_is_self_enforced_before_successor_queue(self):
        start = self.text.index("- name: Publish sanitized cloud-session receipt")
        enforce = self.text.index(
            "- name: Enforce sanitized v2 cloud-session receipt acceptance"
        )
        queue = self.text.index("- name: Queue successor bounded session")
        self.assertLess(start, enforce)
        self.assertLess(enforce, queue)
        section = self.text[enforce:queue]
        self.assertIn("scripts/mmibkr_cloud_session_acceptance_v1.py", section)
        self.assertIn("--receipt \"$RUNNER_TEMP/mmibkr-cloud-session-receipt.json\"", section)
        self.assertIn("--mode first-post-fix", section)
        self.assertIn("--expected-public-sha \"$GITHUB_SHA\"", section)
        self.assertIn("--expected-private-sha \"$PRIVATE_HEAD\"", section)
        self.assertIn("MMIBKR_CLOUD_V2_RECEIPT_ACCEPTED=1", section)

    def test_durable_receipt_remains_sanitized(self):
        start = self.text.index("- name: Publish sanitized cloud-session receipt")
        end = self.text.index("- name: Queue successor bounded session")
        section = self.text[start:end]
        for forbidden in (
            "account_summary",
            "open_trades",
            "fills",
            "avg_cost",
            "localSymbol",
            "conId",
            "IBKR_PAPER_PASSWORD",
            "TWS_PASSWORD",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        ):
            self.assertNotIn(forbidden, section)
        self.assertIn("'account_state_included': False", section)
        self.assertIn("'positions_included': False", section)
        self.assertIn("'orders_included': False", section)
        self.assertIn("'credentials_included': False", section)


if __name__ == "__main__":
    unittest.main()
