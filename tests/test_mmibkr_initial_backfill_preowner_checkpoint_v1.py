from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class InitialBackfillPreownerCheckpointTests(unittest.TestCase):
    def test_checkpoint_is_built_and_roundtripped_before_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        ingest = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        build = text.index("- name: Build canonical initial-backfill checkpoint before owner")
        save = text.index("- name: Save canonical initial-backfill checkpoint before owner")
        remove = text.index(
            "- name: Remove local initial-backfill checkpoint before round-trip proof"
        )
        restore = text.index("- name: Restore exact initial-backfill checkpoint before owner")
        enforce = text.index(
            "- name: Enforce exact initial-backfill checkpoint round-trip before owner"
        )
        owner = text.index("- name: Run bounded selected-runtime cloud owner")

        self.assertLess(ingest, build)
        self.assertLess(build, save)
        self.assertLess(save, remove)
        self.assertLess(remove, restore)
        self.assertLess(restore, enforce)
        self.assertLess(enforce, owner)

    def test_preowner_checkpoint_uses_existing_canonical_owner_and_cache_namespace(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Build canonical initial-backfill checkpoint before owner")
        end = text.index("- name: Run bounded selected-runtime cloud owner")
        section = text[start:end]

        self.assertIn(
            "python scripts/operator/runtime_market_data_cache_checkpoint_v1.py",
            section,
        )
        self.assertIn(
            "CHECKPOINT_CACHE_PREFIX }}\${{ github.run_id }}-\${{ env.PRIVATE_HEAD }}-initial-backfill-preowner",
            section,
        )
        self.assertIn("fail-on-cache-miss: true", section)
        self.assertIn("test \"$CACHE_HIT\" = 'true'", section)
        self.assertIn('test "$actual_sha256" = "$EXPECTED_SHA256"', section)
        self.assertIn("MMIBKR_INITIAL_BACKFILL_PREOWNER_CHECKPOINT_SAVED=1", section)

    def test_v2_receipt_records_preowner_checkpoint_identity(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("mmibkr.selected_runtime_cloud_session_receipt.v2", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PREOWNER_CHECKPOINT_SAVED", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PREOWNER_CHECKPOINT_SHA256", text)
        self.assertIn("MMIBKR_RECEIPT_INITIAL_BACKFILL_PREOWNER_CHECKPOINT_CACHE_KEY", text)
        self.assertIn("'preowner_checkpoint_saved':", text)
        self.assertIn("'preowner_checkpoint_sha256':", text)
        self.assertIn("'preowner_checkpoint_cache_key':", text)


if __name__ == "__main__":
    unittest.main()
