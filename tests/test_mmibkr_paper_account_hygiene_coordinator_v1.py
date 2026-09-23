from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-paper-account-hygiene-coordinator-r1.yml"


class PaperAccountHygieneCoordinatorTests(unittest.TestCase):
    def text(self) -> str:
        return WORKFLOW.read_text(encoding="utf-8")

    def test_merge_does_not_execute_hygiene_without_explicit_fire_or_dispatch(self):
        text = self.text()
        self.assertIn("pull_request:", text)
        self.assertIn("if: ${{ github.event_name == 'pull_request' }}", text)
        self.assertIn("if: ${{ github.event_name != 'pull_request' }}", text)
        self.assertIn(
            "rendezvous/fire/mmibkr-paper-account-hygiene-coordinator-r1.json",
            text,
        )
        self.assertNotIn(
            "- '.github/workflows/mmibkr-paper-account-hygiene-coordinator-r1.yml'\n  push:",
            text,
        )

    def test_coordinator_binds_exact_validated_producer_and_ownership_runtime_source(self):
        text = self.text()
        self.assertIn(
            "PRODUCER_SOURCE_SHA: 6a20403d771cbcf40ae475f8f66979973debe57b",
            text,
        )
        self.assertIn(
            "PRODUCER_ARCHIVE_SHA256: f2177a3caebee041a9e15cac9735a0d114eedf183e3df904cfde84866719b82f",
            text,
        )
        self.assertIn("PRODUCER_ARCHIVE_BYTES: '66375251'", text)
        self.assertIn(
            "RUNTIME_SOURCE_SHA: 35e6b44e5c2618f780a84c1c204fe14c76bdf0e5",
            text,
        )
        self.assertIn("scripts/mmibkr_source_vault_consumer_v1.py", text)
        self.assertIn("fleet_authority_exact_sha_encrypted_snapshot_vault", text)

    def test_fresh_operator_snapshot_is_required_and_private(self):
        text = self.text()
        self.assertIn("/v1/operator-snapshot-read", text)
        self.assertIn("audience=mmibkr-operator-console", text)
        self.assertIn("operator snapshot runtime source mismatch", text)
        self.assertIn("operator snapshot contains open broker orders", text)
        self.assertIn("private_snapshot_published': False", text)
        self.assertIn("private_source_published': False", text)

    def test_private_producer_receives_shell_array_arguments_not_literal_text(self):
        text = self.text()
        self.assertIn('ibkr_remote_account_hygiene_slot_v1.py "${args[@]}"', text)
        self.assertNotIn('ibkr_remote_account_hygiene_slot_v1.py "\\${args[@]}"', text)

    def test_preflight_is_default_and_execute_is_explicit(self):
        text = self.text()
        self.assertIn("default: false", text)
        self.assertIn("HYGIENE_EXECUTE=", text)
        self.assertIn("args+=(--execute)", text)
        self.assertIn("--operator-approved", text)
        self.assertIn("MMIBKR_PAPER_ACCOUNT_HYGIENE_ACK_V1", text)
        self.assertIn("preflight unexpectedly executed broker action", text)
        self.assertIn("PAPER_ACCOUNT_HYGIENE_RECONCILED", text)

    def test_workflow_does_not_own_direct_broker_or_live_authority(self):
        text = self.text()
        self.assertIn("ENABLE_LIVE_TRADING: '0'", text)
        self.assertIn("'direct_broker_client_used'", text)
        self.assertIn("'live_execution_allowed'", text)
        self.assertIn("'global_cancel_allowed'", text)
        self.assertNotIn("IBKR_PAPER_USERNAME", text)
        self.assertNotIn("IBKR_PAPER_PASSWORD", text)
        self.assertNotIn("/strategy/ibkr-paper-flatten-submit-suite", text)
        self.assertNotIn("placeOrder(", text)


if __name__ == "__main__":
    unittest.main()
