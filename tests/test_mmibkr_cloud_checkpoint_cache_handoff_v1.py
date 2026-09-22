from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class CloudCheckpointCacheHandoffTests(unittest.TestCase):
    def test_checkpoint_is_runner_readable_before_cache_save(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Build sanitized successor checkpoint")
        end = text.index("- name: Save sanitized successor checkpoint cache")
        section = text[start:end]

        self.assertIn('uid="$(id -u)"', section)
        self.assertIn('gid="$(id -g)"', section)
        self.assertIn('chown ${uid}:${gid} /checkpoint/latest.tgz', section)
        self.assertIn('chmod 600 /checkpoint/latest.tgz', section)
        self.assertIn('[ -r "$checkpoint" ]', section)
        self.assertIn("MMIBKR_CHECKPOINT_CACHE_READY=1", section)
        self.assertLess(section.index("chown "), section.index("sha256sum"))

    def test_checkpoint_cache_save_remains_sanitized_handoff_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Save sanitized successor checkpoint cache")
        end = text.index("- name: Enforce successful selected-runtime cloud session")
        section = text[start:end]

        self.assertIn("actions/cache/save@", section)
        self.assertIn("steps.checkpoint.outputs.ready == 'true'", section)
        self.assertIn("CHECKPOINT_CACHE_PREFIX", text)
        self.assertIn("Confirm sanitized successor checkpoint cache saved", text)
        self.assertIn("MMIBKR_CHECKPOINT_CACHE_SAVED=1", text)
        self.assertIn("sha256=$checkpoint_sha256", text)
        self.assertIn("Remove local checkpoint before cache round-trip proof", text)
        self.assertIn("Restore just-saved checkpoint cache for round-trip proof", text)
        self.assertIn("fail-on-cache-miss: true", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("steps.verify_checkpoint_cache.outputs.cache-hit", text)
        self.assertIn("EXPECTED_CHECKPOINT_SHA256", text)
        self.assertIn("saved=false", text)
        self.assertIn("saved=true", text)
        self.assertIn('echo "saved=$saved" >> "$GITHUB_OUTPUT"', text)
        self.assertIn("MMIBKR_CHECKPOINT_CACHE_ROUNDTRIP_SHA256=", text)
        self.assertIn("MMIBKR_CHECKPOINT_CACHE_SAVED=0", text)
        self.assertIn("steps.checkpoint_saved.outputs.saved", text)

    def test_explicit_predecessor_restore_is_exact_and_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("expected_checkpoint_cache_key", text)
        self.assertIn("expected_checkpoint_sha256", text)
        self.assertIn(
            "expected_checkpoint_cache_key and expected_checkpoint_sha256 must be supplied together",
            text,
        )
        self.assertIn("- name: Restore exact expected predecessor checkpoint cache", text)
        self.assertIn("fail-on-cache-miss: true", text)
        self.assertIn(
            'test "$RESTORED_CACHE_KEY" = "$EXPECTED_CHECKPOINT_KEY"',
            text,
        )
        self.assertIn(
            'test "$restored_sha256" = "$EXPECTED_CHECKPOINT_SHA256"',
            text,
        )
        self.assertIn("MMIBKR_EXPECTED_PREDECESSOR_CHECKPOINT_MATCH=1", text)
        self.assertIn("expected_predecessor_checkpoint_cache_key", text)
        self.assertIn("expected_predecessor_checkpoint_sha256", text)
        self.assertIn("expected_predecessor_checkpoint_match", text)

    def test_exact_predecessor_mode_disables_latest_prefix_fallback(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        exact = text.index("- name: Restore exact expected predecessor checkpoint cache")
        latest = text.index("- name: Restore latest sanitized checkpoint cache")
        restore = text.index(
            "- name: Restore canonical market-data and terminal-continuity state"
        )
        section = text[exact:restore]
        self.assertLess(exact, latest)
        self.assertIn(
            "if: ${{ env.EXPECTED_PREDECESSOR_CHECKPOINT_KEY != '' }}",
            section,
        )
        self.assertIn(
            "if: ${{ env.EXPECTED_PREDECESSOR_CHECKPOINT_KEY == '' }}",
            section,
        )

    def test_workflow_dispatch_rejects_unpinned_successor_before_concurrency(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("expected_checkpoint_cache_key:", text)
        self.assertIn("expected_checkpoint_sha256:", text)
        self.assertIn("allow_unpinned_bootstrap:", text)
        self.assertIn("print('unpinned_dispatch_rejected')", text)
        self.assertIn("print('invalid_dispatch')", text)
        self.assertIn("reject_unpinned_dispatch:", text)
        self.assertIn(
            "Reject unpinned or invalid workflow dispatch before owner concurrency",
            text,
        )
        reject = text.index("  reject_unpinned_dispatch:")
        runtime = text.index("  runtime:")
        self.assertLess(reject, runtime)

    def test_healthy_self_handoff_carries_new_saved_checkpoint_identity(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Queue successor bounded session")
        end = text.index("- name: Destroy private runtime material")
        section = text[start:end]
        self.assertIn(
            "SUCCESSOR_CHECKPOINT_CACHE_KEY: ${{ steps.checkpoint_saved.outputs.saved_cache_key }}",
            section,
        )
        self.assertIn(
            "SUCCESSOR_CHECKPOINT_SHA256: ${{ steps.checkpoint_saved.outputs.saved_sha256 }}",
            section,
        )
        self.assertIn('test -n "$SUCCESSOR_CHECKPOINT_CACHE_KEY"', section)
        self.assertIn('test -n "$SUCCESSOR_CHECKPOINT_SHA256"', section)
        self.assertIn("'expected_checkpoint_cache_key':", section)
        self.assertIn("'expected_checkpoint_sha256':", section)
        self.assertIn("'allow_unpinned_bootstrap': False", section)

    def test_successor_terminal_continuity_is_fail_closed_before_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("require_terminal_continuity:", text)
        self.assertIn(
            "require_terminal_continuity requires an exact predecessor checkpoint identity",
            text,
        )
        terminal = text.index("- name: Enforce predecessor terminal continuity before owner")
        ingest = text.index(
            "- name: Consume proven initial selected-runtime backfill through canonical ingest"
        )
        owner = text.index("- name: Run bounded selected-runtime cloud owner")
        self.assertLess(terminal, ingest)
        self.assertLess(terminal, owner)
        section = text[terminal:ingest]
        self.assertIn("docker run --rm -i", section)
        self.assertIn("terminal_boundaries.json", section)
        self.assertIn(
            "mmibkr.selected_runtime_cloud_cycle_terminal_ledger.v1",
            section,
        )
        self.assertIn("predecessor terminal continuity has no terminal entries", section)
        self.assertIn("MMIBKR_PREDECESSOR_TERMINAL_CONTINUITY_READY=1", section)

    def test_healthy_self_handoff_requires_terminal_continuity_recursively(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Queue successor bounded session")
        end = text.index("- name: Destroy private runtime material")
        section = text[start:end]
        self.assertIn("'require_terminal_continuity': True", section)

    def test_private_runtime_cleanup_still_destroys_checkpoint(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        cleanup = text[text.index("- name: Destroy private runtime material") :]
        self.assertIn('"$RUNNER_TEMP/mmibkr-checkpoint"', cleanup)
        self.assertIn("MMIBKR_PRIVATE_RUNTIME_MATERIAL_DESTROYED=1", cleanup)


if __name__ == "__main__":
    unittest.main()
