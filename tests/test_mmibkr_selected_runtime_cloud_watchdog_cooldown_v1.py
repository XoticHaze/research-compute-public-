from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class SelectedRuntimeCloudWatchdogCooldownV1Tests(unittest.TestCase):
    def test_three_recent_consecutive_failures_suppress_dispatch(self):
        result = evaluate_b1_failure_cooldown(
            [
                run_row(3, minutes_ago=5),
                run_row(2, minutes_ago=10),
                run_row(1, minutes_ago=15),
            ],
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
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 3)
        self.assertIsNone(result["retry_after_utc"])

    def test_active_b1_dependency_run_suppresses_duplicate_owner_dispatch(self):
        result = evaluate_b1_failure_cooldown(
            [run_row(9, minutes_ago=1, status="in_progress", conclusion=None)],
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
            now=NOW,
        )
        self.assertFalse(result["suppress"])
        self.assertEqual(result["consecutive_failure_count"], 2)


if __name__ == "__main__":
    unittest.main()
