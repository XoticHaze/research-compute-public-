from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-initial-backfill-ingest-r1.yml"


class InitialBackfillIngestJobTests(unittest.TestCase):
    def test_exact_source_and_artifact_are_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "CANONICAL_SOURCE_REF: d81df85788ebb6be6d4d69b9b9a537be96f16507",
            text,
        )
        self.assertIn("INITIAL_BACKFILL_RUN_ID: '35407829303'", text)
        self.assertIn(
            "INITIAL_BACKFILL_ARTIFACT: ibkr-cloudflare-readonly-b1-35407829303",
            text,
        )
        self.assertIn('gh run download "$INITIAL_BACKFILL_RUN_ID"', text)

    def test_real_artifact_uses_existing_canonical_private_owners(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "python scripts/operator/selected_runtime_initial_backfill_ingest_v1.py",
            text,
        )
        self.assertIn(
            "python scripts/operator/runtime_market_data_cache_checkpoint_v1.py",
            text,
        )
        self.assertIn("--bars /input/ibkr-forward-bars-v2.jsonl", text)
        self.assertIn("--handoff /input/ibkr-post-auth-handoff.json", text)
        self.assertIn(
            "--fleet-receipt /input/ibkr-cloudflare-envelope-receipt.json",
            text,
        )

    def test_warmup_thresholds_and_authority_boundaries_are_enforced(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("'AMAT': ('target_rows', 400)", text)
        self.assertIn("'APH': ('target_rows', 400)", text)
        self.assertIn("'MNQ': ('source_rows', 4800)", text)
        self.assertIn("MNQ target_rows below required warmup", text)
        self.assertIn("broker action boundary violated", text)
        self.assertIn("execution contract mutation boundary violated", text)
        self.assertIn("live execution boundary violated", text)
        self.assertNotIn("placeOrder", text)
        self.assertNotIn("cancelOrder", text)
        self.assertNotIn("globalCancel", text)

    def test_checkpoint_enters_normal_forward_owner_cache_namespace(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "CHECKPOINT_CACHE_PREFIX: mmibkr-selected-runtime-cloud-checkpoint-v1-",
            text,
        )
        self.assertIn("Restore latest sanitized canonical checkpoint if available", text)
        self.assertIn("Save canonical checkpoint into normal forward-owner cache namespace", text)
        self.assertIn("Restore just-saved canonical checkpoint", text)
        self.assertIn("fail-on-cache-miss: true", text)
        self.assertIn("MMIBKR_INITIAL_BACKFILL_CHECKPOINT_SAVED=1", text)

    def test_receipt_is_sanitized_and_cleanup_is_required(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("mmibkr.initial_backfill_canonical_ingest_receipt.v1", text)
        self.assertIn("'account_state_included': False", text)
        self.assertIn("'positions_included': False", text)
        self.assertIn("'orders_included': False", text)
        self.assertIn("'credentials_included': False", text)
        self.assertIn("'private_source_included': False", text)
        self.assertIn("MMIBKR_INITIAL_BACKFILL_PRIVATE_RUNTIME_MATERIAL_DESTROYED=1", text)


if __name__ == "__main__":
    unittest.main()
