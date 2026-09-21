from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "5aeb0370a18c4c941852c7454706ba9ffa28da68"


class CloudOwnerReusableVaultContractTests(unittest.TestCase):
    def test_owner_uses_reusable_vault_and_ephemeral_same_repo_control_token(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/mmibkr_source_vault_consumer_v1.py", text)
        self.assertIn("--public-repo XoticHaze/mm-ibkr-runtime", text)
        self.assertIn("--public-branch mmibkr-source-vault", text)
        self.assertIn(SOURCE_SHA, text)
        self.assertIn("IBKR_REMOTE_EXCHANGE_TOKEN: ${{ github.token }}", text)
        self.assertNotIn("secrets.IBKR_REMOTE_EXCHANGE_TOKEN", text)
        self.assertNotIn("python scripts/mmibkr_cloud_source_exchange_consumer_v1.py", text)
        self.assertIn("ENABLE_LIVE_TRADING=0", text)

    def test_cleanup_recovers_root_owned_outputs_before_destroy(self):
        text = (
            ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('MMIBKR_PRIVATE_RUNTIME_MATERIAL_DESTROYED=1', text)
        self.assertIn('chown -R ${uid}:${gid} /cleanup-data /cleanup-checkpoint', text)
        self.assertIn('private runtime cleanup residue', text)
        self.assertNotIn(
            'set +e\n          docker image rm "mmibkr-cloud:${GITHUB_RUN_ID}"',
            text,
        )
    def test_session_success_gate_rejects_all_failed_cycle_session(self):
        text = (
            ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Enforce successful selected-runtime cloud session", text)
        self.assertIn("int(node.get('success_count') or 0) >= 1", text)
        self.assertIn("node.get('checkpoint_handoff_ready') is True", text)
        self.assertIn("last_cycle.get('ok') is True", text)
        self.assertIn("'session_accepted': session_accepted", text)

    def test_watchdog_restarts_exact_accepted_source_not_private_main(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml").read_text(encoding="utf-8")
        self.assertIn("'source_ref':'" + SOURCE_SHA + "'", text)
        self.assertNotIn("'source_ref':'main'", text)

    def test_owner_refreshes_stale_handoff_to_current_promoted_source(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml").read_text(encoding="utf-8")
        self.assertIn("CANONICAL_SOURCE_REF: " + SOURCE_SHA, text)
        self.assertIn("requested_source_ref = str(", text)
        self.assertIn("source_ref = canonical_source_ref", text)
        self.assertIn("MMIBKR_CLOUD_SOURCE_REFRESHED_FROM=", text)
        self.assertIn("MMIBKR_CLOUD_SOURCE_REFRESHED_TO=", text)

    def test_successor_does_not_perpetuate_stale_source_identity(self):
        text = (ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml").read_text(encoding="utf-8")
        marker = "      - name: Queue successor bounded session"
        start = text.index(marker)
        successor = text[start:]
        self.assertNotIn("'source_ref': os.environ['REQUEST_SOURCE_REF']", successor)
        self.assertIn("'session_seconds': os.environ['SESSION_SECONDS']", successor)


if __name__ == "__main__":
    unittest.main()
