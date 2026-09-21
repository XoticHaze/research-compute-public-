from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class InitialBackfillCanonicalIngestWorkflowTests(unittest.TestCase):
    def test_exact_proven_public_artifact_is_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("INITIAL_BACKFILL_RUN_ID: '35407829303'", text)
        self.assertIn(
            "INITIAL_BACKFILL_ARTIFACT: ibkr-cloudflare-readonly-b1-35407829303",
            text,
        )
        self.assertIn('gh run download "$INITIAL_BACKFILL_RUN_ID"', text)
        self.assertIn("--name \"$INITIAL_BACKFILL_ARTIFACT\"", text)

    def test_artifact_crosses_existing_private_canonical_ingest_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]

        self.assertIn(
            "scripts/operator/selected_runtime_initial_backfill_ingest_v1.py",
            section,
        )
        self.assertIn("--data-root /app/data", section)
        self.assertIn("--bars /input/ibkr-forward-bars-v2.jsonl", section)
        self.assertIn("--handoff /input/ibkr-post-auth-handoff.json", section)
        self.assertIn(
            "--fleet-receipt /input/ibkr-cloudflare-envelope-receipt.json",
            section,
        )
        self.assertIn("all_warmups_ready", section)
        self.assertIn("MMIBKR_INITIAL_BACKFILL_INGEST=accepted", section)
        self.assertLess(
            text.index(
                "- name: Consume proven initial selected-runtime backfill through canonical ingest"
            ),
            text.index("- name: Run bounded selected-runtime cloud owner"),
        )

    def test_warmup_and_authority_guards_are_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]

        self.assertIn("AMAT target coverage below warmup", section)
        self.assertIn("APH target coverage below warmup", section)
        self.assertIn("MNQ source coverage below warmup", section)
        self.assertIn("MNQ target coverage below warmup", section)
        self.assertIn("broker_action", section)
        self.assertIn("runtime_execution_contract_mutated", section)
        self.assertIn("live_execution_allowed", section)
        self.assertNotIn("placeOrder", section)
        self.assertNotIn("cancelOrder", section)
        self.assertNotIn("globalCancel", section)

    def test_existing_canonical_checkpoint_is_restored_before_ingest_and_saved_after(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        restore = text.index("- name: Restore canonical market-data and terminal-continuity state")
        ingest = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        owner = text.index("- name: Run bounded selected-runtime cloud owner")
        checkpoint = text.index("- name: Build sanitized successor checkpoint")
        save = text.index("- name: Save sanitized successor checkpoint cache")

        self.assertLess(restore, ingest)
        self.assertLess(ingest, owner)
        self.assertLess(owner, checkpoint)
        self.assertLess(checkpoint, save)
        self.assertIn("CHECKPOINT_CACHE_PREFIX: mmibkr-selected-runtime-cloud-checkpoint-v1-", text)

    def test_sanitized_session_receipt_records_the_crossing(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_READY", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PERFORMED", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PUBLIC_RUN_ID", text)
        self.assertIn("receipt['initial_backfill_ingest']", text)
        self.assertIn("'artifact_name': 'ibkr-cloudflare-readonly-b1-35407829303'", text)
        self.assertIn("'broker_action': False", text)
        self.assertIn("'runtime_execution_contract_mutated': False", text)
        self.assertIn("'live_execution_allowed': False", text)


if __name__ == "__main__":
    unittest.main()
