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

    def test_private_runtime_cleanup_still_destroys_checkpoint(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        cleanup = text[text.index("- name: Destroy private runtime material") :]
        self.assertIn('"$RUNNER_TEMP/mmibkr-checkpoint"', cleanup)
        self.assertIn("MMIBKR_PRIVATE_RUNTIME_MATERIAL_DESTROYED=1", cleanup)


if __name__ == "__main__":
    unittest.main()
