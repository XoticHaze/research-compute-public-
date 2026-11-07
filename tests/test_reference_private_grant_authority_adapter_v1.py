"""Real P-256 non-PHI one-use private grant tests; no external accounts."""
from __future__ import annotations
import copy
import unittest

from scripts.reference_release_grant_v1 import (
    generate_authority_signer, ExpectedGrant, verify_grant,
)
from scripts.reference_private_grant_authority_adapter_v1 import (
    PrivateGrantPolicy, NotAuthorized, issue_once,
)

NOW = 1700000000
HASH40 = "b" * 40
IDENTITY = "c" * 64
WORKER = "sha256:" + "d" * 64
BROKER = "sha256:" + "e" * 64
GRANT = "private-grant-0123456789abcdef"


class OneTimeJournal:
    def __init__(self):
        self.seen = {}
        self.calls = 0

    def consume_once(self, *, grant_id, payload_sha256):
        self.calls += 1
        if grant_id in self.seen:
            return False
        self.seen[grant_id] = payload_sha256
        return True


class PrivateGrantAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.private, self.public, self.key_id = generate_authority_signer()
        self.policy = PrivateGrantPolicy(
            authority_public_b64=self.public,
            authority_key_id=self.key_id,
            broker_key_id=BROKER,
            harness_sha=HASH40,
            identity_sha256=IDENTITY,
            max_seconds=300,
        )
        self.request = {
            "grant_id": GRANT,
            "run_id": "42354355024",
            "run_attempt": "1",
            "harness_sha": HASH40,
            "identity_sha256": IDENTITY,
            "worker_key_id": WORKER,
            "broker_key_id": BROKER,
            "not_before": NOW - 10,
            "admission_not_after": NOW + 150,
        }
        self.journal = OneTimeJournal()

    def issue(self, request=None, policy=None, private=None, journal=None):
        return issue_once(
            self.request if request is None else request,
            policy=self.policy if policy is None else policy,
            protected_private_key_b64=self.private if private is None else private,
            journal=self.journal if journal is None else journal,
            clock=lambda: NOW,
        )

    def test_real_private_p256_release_grant_signed_and_verified(self):
        wrapper = self.issue()
        self.assertEqual(set(wrapper), {
            "payload_b64", "signature_b64", "signer_key_id", "signature_format",
        })
        self.assertEqual(wrapper["signer_key_id"], self.key_id)
        self.assertNotIn(self.private, str(wrapper))
        self.assertNotIn(self.public, str(wrapper))
        result = verify_grant(
            wrapper,
            authority_public_b64=self.public,
            expected=ExpectedGrant(
                grant_id=GRANT,
                run_id=self.request["run_id"],
                run_attempt="1",
                harness_sha=HASH40,
                identity_sha256=IDENTITY,
                worker_key_id=WORKER,
                broker_key_id=BROKER,
            ),
            now=NOW,
            max_admission_seconds=300,
        )
        self.assertEqual(result["grant_id"], GRANT)
        self.assertEqual(self.journal.calls, 1)

    def test_replay_refused_even_with_same_signed_payload(self):
        self.issue()
        with self.assertRaisesRegex(NotAuthorized, "^PRIVATE_GRANT_ISSUE_REJECTED$"):
            self.issue()
        self.assertEqual(self.journal.calls, 2)
        self.assertEqual(len(self.journal.seen), 1)

    def test_wrong_broker_identity_or_harness_refused_before_spending(self):
        for k, value in (
            ("broker_key_id", "sha256:" + "f" * 64),
            ("harness_sha", "0" * 40),
            ("identity_sha256", "0" * 64),
            ("worker_key_id", "sha256:not-a-key"),
            ("run_attempt", "0"),
        ):
            with self.subTest(field=k):
                changed = dict(self.request, **{k: value})
                with self.assertRaisesRegex(NotAuthorized, "PRIVATE_GRANT_ISSUE_REJECTED"):
                    self.issue(changed)
        self.assertEqual(self.journal.calls, 0)

    def test_expired_overlong_or_future_not_before_rejected(self):
        for attrs in (
            {"admission_not_after": NOW - 1},
            {"admission_not_after": NOW + 1000},
            {"not_before": NOW + 100},
            {"not_before": NOW - 100},
        ):
            with self.assertRaisesRegex(NotAuthorized, "PRIVATE_GRANT_ISSUE_REJECTED"):
                self.issue(dict(self.request, **attrs))
        self.assertEqual(self.journal.calls, 0)

    def test_no_arbitrary_user_fields_or_unreviewed_bearer(self):
        for added in (
            {"private_key": self.private},
            {"root_command": "sudo"},
            {"plaintext": "sensitive"},
        ):
            with self.assertRaisesRegex(NotAuthorized, "PRIVATE_GRANT_ISSUE_REJECTED"):
                self.issue(dict(self.request, **added))
        self.assertEqual(self.journal.calls, 0)

    def test_reject_key_mismatch_before_spending(self):
        other, _, _ = generate_authority_signer()
        with self.assertRaisesRegex(NotAuthorized, "PRIVATE_GRANT_ISSUE_REJECTED"):
            self.issue(private=other)
        self.assertEqual(self.journal.calls, 0)

    def test_atomic_journal_error_never_releases_signed_grant(self):
        class Failing:
            def consume_once(self, **_):
                raise RuntimeError("private-journal-not-accessible-secret-info")
        with self.assertRaisesRegex(NotAuthorized, "^PRIVATE_GRANT_ISSUE_REJECTED$"):
            self.issue(journal=Failing())
        self.assertEqual(self.journal.calls, 0)

    def test_invalid_signature_input_and_no_public_owner_claim(self):
        policy = PrivateGrantPolicy(
            authority_public_b64=self.public,
            authority_key_id="sha256:" + "1" * 64,
            broker_key_id=BROKER,
            harness_sha=HASH40,
            identity_sha256=IDENTITY,
            max_seconds=300,
        )
        with self.assertRaisesRegex(NotAuthorized, "PRIVATE_GRANT_ISSUE_REJECTED"):
            self.issue(policy=policy)
        self.assertEqual(self.journal.calls, 0)


if __name__ == "__main__":
    unittest.main()
