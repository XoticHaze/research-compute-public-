from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class CheckpointAcceptanceJobTests(unittest.TestCase):
    def test_acceptance_fire_path_is_distinct_from_owner_fire_path(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "rendezvous/fire/mmibkr-selected-runtime-cloud-checkpoint-acceptance-r1",
            text,
        )
        self.assertIn("checkpoint_acceptance:", text)
        self.assertIn(
            "group: mmibkr-selected-runtime-cloud-checkpoint-acceptance-r1",
            text,
        )
        self.assertIn(
            "group: mmibkr-selected-runtime-cloud-r1",
            text,
        )

    def test_route_job_resolves_checkpoint_acceptance_from_exact_git_diff(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        route_start = text.index("  route:")
        contract_start = text.index("  contract:")
        route = text[route_start:contract_start]
        self.assertIn("fetch-depth: 2", route)
        self.assertIn("git diff-tree --no-commit-id --name-only -r HEAD^ HEAD", route)
        self.assertIn(
            "rendezvous/fire/mmibkr-selected-runtime-cloud-checkpoint-acceptance-r1",
            route,
        )
        self.assertIn('mode="checkpoint_acceptance"', route)

    def test_owner_and_acceptance_jobs_use_route_output(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        runtime_start = text.index("  runtime:")
        acceptance_start = text.index("  checkpoint_acceptance:")
        runtime = text[runtime_start:acceptance_start]
        acceptance = text[acceptance_start:]
        self.assertIn("needs.route.outputs.mode == 'owner'", runtime)
        self.assertIn("- route", runtime)
        self.assertIn("needs.route.outputs.mode == 'checkpoint_acceptance'", acceptance)
        self.assertIn("- route", acceptance)

    def test_acceptance_validation_heredoc_keeps_stdin_attached(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  checkpoint_acceptance:"):]
        self.assertIn("docker run --rm -i", section)
        self.assertIn("python - <<'PY' > \"$RUNNER_TEMP/mmibkr-checkpoint-acceptance.env\"", section)

    def test_acceptance_proves_exact_backfill_checkpoint_roundtrip_without_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  checkpoint_acceptance:"):]
        self.assertIn(
            "scripts/operator/selected_runtime_initial_backfill_ingest_v1.py",
            section,
        )
        self.assertIn("-w /app", section)
        self.assertIn("-e PYTHONPATH=/app", section)
        self.assertIn(
            "scripts/operator/runtime_market_data_cache_checkpoint_v1.py",
            section,
        )
        self.assertIn("- name: Save checkpoint", section)
        self.assertIn("- name: Delete local checkpoint copy", section)
        self.assertIn("- name: Restore exact saved checkpoint", section)
        self.assertIn("- name: Verify exact restored SHA256", section)
        self.assertIn('test "$CACHE_HIT" = \'true\'', section)
        self.assertIn('test "$actual" = "$EXPECTED_SHA256"', section)
        self.assertIn("'paper_owner_started': False", section)
        self.assertNotIn("selected_runtime_cloud_daemon_v1.py", section)

    def test_acceptance_is_exact_source_exact_artifact_and_fail_closed(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  checkpoint_acceptance:"):]
        self.assertIn(
            "CANONICAL_SOURCE_REF: 8a82107be253c3facd3b090cf752bc51b3a8ef8d",
            section,
        )
        self.assertIn('gh run download "$INITIAL_BACKFILL_RUN_ID"', section)
        self.assertIn("--name \"$INITIAL_BACKFILL_ARTIFACT\"", section)
        self.assertIn("AMAT_TARGET_ROWS", section)
        self.assertIn("APH_TARGET_ROWS", section)
        self.assertIn("MNQ_SOURCE_ROWS", section)
        self.assertIn("MNQ_TARGET_ROWS", section)
        self.assertIn("broker action boundary violated", section)
        self.assertIn("execution contract mutation boundary violated", section)
        self.assertIn("live execution boundary violated", section)

    def test_receipt_is_sanitized_and_durable(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        section = text[text.index("  checkpoint_acceptance:"):]
        self.assertIn("mmibkr.backfill_checkpoint_acceptance.v1", section)
        self.assertIn("'exact_saved_checkpoint_restored': True", section)
        self.assertIn("'exact_sha256_verified': True", section)
        self.assertIn("'broker_action': False", section)
        self.assertIn("'paper_owner_started': False", section)
        self.assertIn("'live_execution_allowed': False", section)
        self.assertIn("'credentials_included': False", section)
        self.assertIn("'private_source_included': False", section)


if __name__ == "__main__":
    unittest.main()
