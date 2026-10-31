from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from scripts.mmibkr_selected_runtime_cloud_watchdog_cooldown_v1 import (
    evaluate_b1_failure_cooldown,
)


NOW = datetime(2026, 9, 23, 9, 30, tzinfo=timezone.utc)


def run_row(
    run_id: int,
    *,
    minutes_ago: int,
    status: str = "completed",
    conclusion: str | None = "failure",
    branch: str = "ibkr-b1-authority-v1",
    event: str = "workflow_dispatch",
):
    stamp = NOW - timedelta(minutes=minutes_ago)
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "head_branch": branch,
        "event": event,
        "created_at": stamp.isoformat().replace("+00:00", "Z"),
        "updated_at": stamp.isoformat().replace("+00:00", "Z"),
    }


def broker_jobs(*run_ids: int) -> dict[str, list[dict]]:
    """Synthetic GitHub API jobs, bound to exact run and failed broker step."""
    return {
        str(run_id): [{
            "run_id": run_id,
            "conclusion": "failure",
            "steps": [{
                "name": "Prove read-only broker session and historical data fetch",
                "status": "completed",
                "conclusion": "failure",
            }],
        }]
        for run_id in run_ids
    }


def historical_conflict_jobs(*run_ids: int) -> dict[str, list[dict]]:
    """Authenticated GitHub job steps, not caller-written failure labels."""
    return {
        str(run_id): [{
            "run_id": run_id,
            "conclusion": "failure",
            "steps": [
                {"name": "Materialize canonical post-auth broker and forward-data handoff",
                 "status": "completed", "conclusion": "failure"},
                {"name": "Validate and re-emit only the fixed-field historical session-conflict receipt",
                 "status": "completed", "conclusion": "success"},
                {"name": "Publish fixed-field historical session-conflict failure",
                 "status": "completed", "conclusion": "success"},
            ],
        }]
        for run_id in run_ids
    }


class SelectedRuntimeCloudWatchdogCooldownV1Tests(unittest.TestCase):
    def test_three_recent_consecutive_failures_suppress_dispatch(self):
        result = evaluate_b1_failure_cooldown(
            [
                run_row(3, minutes_ago=5),
                run_row(2, minutes_ago=10),
                run_row(1, minutes_ago=15),
            ],
            job_evidence_by_run_id=broker_jobs(1, 2, 3, 4, 5, 9),
            now=NOW,
        )
        self.assertTrue(result["suppress"])
        self.assertEqual(result["reason"], "recent_consecutive_b1_failures")
        self.assertEqual(result["consecutive_failure_count"], 3)
        self.assertEqual(result["latest_run_id"], "3")
        self.assertEqual(result["retry_after_utc"], "2026-09-23T09:55:00Z")

    def test_success_breaks_consecutive_failure_chain(self):
        result = evaluate_b1_failure_cooldown(
            [
                run_row(4, minutes_ago=4),
                run_row(3, minutes_ago=8),
                run_row(2, minutes_ago=12, conclusion="success"),
                run_row(1, minutes_ago=16),
            ],
            job_evidence_by_run_id=broker_jobs(1, 2, 3, 4, 5, 9),
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 2)

    def test_old_failure_cluster_allows_automatic_retry(self):
        result = evaluate_b1_failure_cooldown(
            [
                run_row(3, minutes_ago=35),
                run_row(2, minutes_ago=40),
                run_row(1, minutes_ago=45),
            ],
            job_evidence_by_run_id=broker_jobs(1, 2, 3, 4, 5, 9),
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 3)
        self.assertIsNone(result["retry_after_utc"])

    def test_active_b1_dependency_run_suppresses_duplicate_owner_dispatch(self):
        result = evaluate_b1_failure_cooldown(
            [run_row(9, minutes_ago=1, status="in_progress", conclusion=None)],
            job_evidence_by_run_id=broker_jobs(1, 2, 3, 4, 5, 9),
            now=NOW,
        )
        self.assertTrue(result["suppress"])
        self.assertEqual(result["reason"], "b1_dependency_run_active")
        self.assertEqual(result["latest_run_id"], "9")

    def test_unrelated_branch_and_event_are_ignored(self):
        result = evaluate_b1_failure_cooldown(
            [
                run_row(5, minutes_ago=1, branch="main"),
                run_row(4, minutes_ago=2, event="push"),
                run_row(3, minutes_ago=3),
                run_row(2, minutes_ago=4),
            ],
            job_evidence_by_run_id=broker_jobs(1, 2, 3, 4, 5, 9),
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 2)


    def test_three_verified_fixed_field_different_ip_conflicts_suppress_dispatch(self):
        runs = [run_row(3, minutes_ago=5), run_row(2, minutes_ago=10),
                run_row(1, minutes_ago=15)]
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=historical_conflict_jobs(1, 2, 3),
            now=NOW,
        )
        self.assertTrue(result["suppress"])
        self.assertEqual(result["reason"], "recent_consecutive_b1_failures")
        self.assertEqual(result["consecutive_failure_count"], 3)
        self.assertEqual(result["latest_run_id"], "3")

    def test_unpublished_conflict_receipt_never_claims_broker_failure(self):
        runs = [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)]
        jobs = historical_conflict_jobs(1, 2, 3)
        jobs["1"][0]["steps"][2]["conclusion"] = "skipped"
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=jobs, now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["reason"], "b1_failure_unclassified")
        self.assertEqual(result["consecutive_failure_count"], 0)

    def test_fixed_field_conflict_requires_exact_github_run_identity(self):
        runs = [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)]
        jobs = historical_conflict_jobs(1, 2, 3)
        jobs["1"][0]["run_id"] = 999
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=jobs, now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["reason"], "b1_failure_unclassified")


    def test_watchdog_reads_immutable_session_receipts_from_exchange_branch(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "f'https://api.github.com/repos/{repo}/contents/{path}?ref=rendezvous-exchange'",
            workflow,
        )
        self.assertNotIn(
            "f'https://api.github.com/repos/{repo}/contents/{path}?ref=main'",
            workflow,
        )
        self.assertIn("receipt.get('checkpoint_cache_saved') is True", workflow)
        self.assertIn("saved_key.endswith('-' + canonical_source)", workflow)
        self.assertIn("'require_terminal_continuity':True", workflow)



    def test_three_zero_step_nonstarts_never_trigger_broker_cooldown(self):
        runs = [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)]
        jobs = {str(i): [{"run_id": i, "conclusion": "failure", "steps": []}]
                for i in (3, 2, 1)}
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=jobs, now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["reason"], "b1_failure_unclassified")
        self.assertEqual(result["consecutive_failure_count"], 0)
        self.assertEqual(result["unclassified_failure_run_id"], "1")

    def test_checkout_only_failure_is_not_broker_dependency(self):
        runs = [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)]
        jobs = {
            str(i): [{"run_id": i, "conclusion": "failure", "steps": [
                {"name": "Run actions/checkout@pinned", "status": "completed",
                 "conclusion": "failure"},
            ]}]
            for i in (3, 2, 1)
        }
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=jobs, now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["reason"], "b1_failure_unclassified")

    def test_actual_broker_step_failure_requires_matching_run_identity(self):
        runs = [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)]
        result = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=broker_jobs(1, 2, 3), now=NOW,
        )
        self.assertTrue(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 3)
        wrong = broker_jobs(1, 2, 3)
        wrong["1"][0]["run_id"] = 999
        denied = evaluate_b1_failure_cooldown(
            runs, job_evidence_by_run_id=wrong, now=NOW,
        )
        self.assertFalse(denied["suppress"])
        self.assertEqual(denied["reason"], "b1_failure_unclassified")

    def test_missing_job_evidence_cannot_claim_broker_failure(self):
        result = evaluate_b1_failure_cooldown(
            [run_row(i, minutes_ago=i * 5) for i in (3, 2, 1)],
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["reason"], "b1_failure_unclassified")

    def test_workflow_reads_authenticated_job_steps_not_only_run_summaries(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("/actions/runs/{run_id}/jobs?per_page=100", workflow)
        self.assertIn("job_evidence_by_run_id=job_evidence", workflow)
        self.assertIn("MMIBKR_CLOUD_WATCHDOG=B1_FAILURE_UNCLASSIFIED", workflow)
        self.assertIn("MMIBKR_CLOUD_WATCHDOG=no_current_source_checkpoint", workflow)
        self.assertNotIn("print(jobs_node)", workflow)


if __name__ == "__main__":
    unittest.main()
