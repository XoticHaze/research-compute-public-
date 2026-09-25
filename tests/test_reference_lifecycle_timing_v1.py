import unittest

from scripts.reference_lifecycle_timing_v1 import (
    TimingPolicy,
    TimingRejected,
    admit,
    bind_admission,
    complete,
    validate_intent,
)


class ReferenceLifecycleTimingTests(unittest.TestCase):
    def setUp(self):
        self.policy = TimingPolicy()
        self.t0 = 100000

    def test_five_hour_execution_is_valid_after_five_minute_admission(self):
        validate_intent(
            now=self.t0,
            intent_not_before=self.t0,
            intent_not_after=self.t0 + 8 * 3600,
            execution_seconds=5 * 3600,
            result_return_grace_seconds=1800,
            result_retention_seconds=86400,
            policy=self.policy,
        )
        worker_start = self.t0 + 7 * 3600
        bind_admission(
            now=worker_start,
            intent_not_before=self.t0,
            intent_not_after=self.t0 + 8 * 3600,
            admission_not_after=worker_start + 300,
            policy=self.policy,
        )
        admitted = admit(
            now=worker_start + 30,
            admission_not_after=worker_start + 300,
            execution_seconds=5 * 3600,
            result_return_grace_seconds=1800,
            policy=self.policy,
        )
        self.assertEqual(worker_start + 30 + 5 * 3600, admitted["execution_not_after"])
        self.assertEqual(
            worker_start + 30 + 5 * 3600 + 1800,
            admitted["result_return_not_after"],
        )

    def test_queue_delay_does_not_consume_admission_window(self):
        worker_start = self.t0 + 7 * 3600
        bind_admission(
            now=worker_start,
            intent_not_before=self.t0,
            intent_not_after=self.t0 + 8 * 3600,
            admission_not_after=worker_start + 300,
            policy=self.policy,
        )

    def test_five_hour_admission_ticket_is_rejected(self):
        with self.assertRaisesRegex(TimingRejected, "admission_ttl_too_long"):
            bind_admission(
                now=self.t0,
                intent_not_before=self.t0,
                intent_not_after=self.t0 + 8 * 3600,
                admission_not_after=self.t0 + 5 * 3600,
                policy=self.policy,
            )

    def test_ticket_expiry_only_blocks_not_yet_admitted_start(self):
        with self.assertRaisesRegex(TimingRejected, "admission_expired"):
            admit(
                now=self.t0 + 301,
                admission_not_after=self.t0 + 300,
                execution_seconds=5 * 3600,
                result_return_grace_seconds=1800,
                policy=self.policy,
            )

    def test_result_retention_is_independent(self):
        result = complete(
            now=self.t0 + 5 * 3600,
            result_return_not_after=self.t0 + 5 * 3600 + 1800,
            result_retention_seconds=86400,
            policy=self.policy,
        )
        self.assertEqual(self.t0 + 5 * 3600 + 86400, result["result_retain_until"])


if __name__ == "__main__":
    unittest.main()
