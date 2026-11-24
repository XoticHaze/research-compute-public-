"""Actual broker intent issuer tests: real P256 cryptography, no external secrets."""
from __future__ import annotations
import unittest

from scripts.reference_release_intent_v1 import (
    generate_signer, ExpectedIntent, verify_intent,
)
from scripts.reference_private_intent_authority_adapter_v1 import (
    PrivateIntentPolicy, NotAuthorized, issue_once,
)

NOW = 1700000000
HARNESS = "b" * 40
CALLER = "c" * 64
BROKER = "sha256:" + "e" * 64
GRANT = "private-intent-0123456789abcdef"


class OneTimePrivateJournal:
    def __init__(self):
        self.seen = {}
        self.calls = 0

    def consume_once(self, *, grant_id, payload_sha256):
        self.calls += 1
        if grant_id in self.seen:
            return False
        self.seen[grant_id] = payload_sha256
        return True


class PrivateLiveIntentTests(unittest.TestCase):
    def setUp(self):
        self.private, self.public, self.key_id = generate_signer()
        self.policy = PrivateIntentPolicy(
            authority_public_b64=self.public,
            authority_key_id=self.key_id,
            broker_key_id=BROKER,
            harness_sha=HARNESS,
            caller_policy_sha256=CALLER,
            max_seconds=300,
        )
        self.request = {
            "grant_id": GRANT,
            "caller_policy_sha256": CALLER,
            "harness_sha": HARNESS,
            "broker_key_id": BROKER,
            "not_before": NOW - 10,
            "intent_not_after": NOW + 150,
        }
        self.journal = OneTimePrivateJournal()

    def issue(self, request=None, policy=None, private=None, journal=None):
        return issue_once(
            self.request if request is None else request,
            policy=self.policy if policy is None else policy,
            protected_private_key_b64=self.private if private is None else private,
            journal=self.journal if journal is None else journal,
            clock=lambda: NOW,
        )

    def test_real_live_intent_p256_sign_and_verify_current_broker_schema(self):
        wrapper = self.issue()
        self.assertEqual(set(wrapper), {
            "payload_b64", "signature_b64", "signer_key_id", "signature_format",
        })
        self.assertEqual(wrapper["signer_key_id"], self.key_id)
        self.assertNotIn(self.private, str(wrapper))
        self.assertNotIn(self.public, str(wrapper))
        checked = verify_intent(
            wrapper, authority_public_b64=self.public,
            expected=ExpectedIntent(
                grant_id=GRANT, caller_policy_sha256=CALLER,
                harness_sha=HARNESS, broker_key_id=BROKER,
            ),
            now=NOW, max_intent_seconds=300,
        )
        self.assertEqual(checked["schema"], "reference-release-intent-v1")
        self.assertEqual(checked["grant_id"], GRANT)
        self.assertEqual(self.journal.calls, 1)

    def test_replay_refused_without_returning_signed_bytes(self):
        self.issue()
        with self.assertRaisesRegex(NotAuthorized, "^PRIVATE_INTENT_ISSUE_REJECTED$"):
            self.issue()
        self.assertEqual(self.journal.calls, 2)
        self.assertEqual(len(self.journal.seen), 1)

    def test_wrong_caller_broker_harness_or_grant_refused_before_journal(self):
        for key, bad in (
            ("broker_key_id", "sha256:" + "f" * 64),
            ("harness_sha", "0" * 40),
            ("caller_policy_sha256", "0" * 64),
            ("grant_id", "bad id"),
        ):
            with self.subTest(field=key):
                with self.assertRaisesRegex(NotAuthorized, "PRIVATE_INTENT_ISSUE_REJECTED"):
                    self.issue(dict(self.request, **{key: bad}))
        self.assertEqual(self.journal.calls, 0)

    def test_expired_too_long_or_future_intent_rejected(self):
        for change in (
            {"intent_not_after": NOW - 1},
            {"intent_not_after": NOW + 1000},
            {"not_before": NOW + 100},
            {"not_before": NOW - 100},
            {"intent_not_after": float(NOW+150)},
        ):
            with self.assertRaisesRegex(NotAuthorized, "PRIVATE_INTENT_ISSUE_REJECTED"):
                self.issue(dict(self.request, **change))
        self.assertEqual(self.journal.calls, 0)

    def test_no_extra_fields_or_private_key_in_signed_intent(self):
        for field in ("root_shell", "plaintext", "private_key", "account"):
            with self.assertRaisesRegex(NotAuthorized, "PRIVATE_INTENT_ISSUE_REJECTED"):
                self.issue(dict(self.request, **{field: "secret"}))
        self.assertEqual(self.journal.calls, 0)

    def test_wrong_private_signer_cannot_consume_approval(self):
        private, _, _ = generate_signer()
        with self.assertRaisesRegex(NotAuthorized, "PRIVATE_INTENT_ISSUE_REJECTED"):
            self.issue(private=private)
        self.assertEqual(self.journal.calls, 0)

    def test_atomic_journal_exception_denies_without_secret_error(self):
        class BrokenJournal:
            def consume_once(self, **_):
                raise RuntimeError("sensitive-private-backend-location")
        with self.assertRaisesRegex(NotAuthorized, "^PRIVATE_INTENT_ISSUE_REJECTED$"):
            self.issue(journal=BrokenJournal())
        self.assertEqual(self.journal.calls, 0)

    def test_unapproved_authority_key_cannot_issue(self):
        policy = PrivateIntentPolicy(
            authority_public_b64=self.public,
            authority_key_id="sha256:" + "1" * 64,
            broker_key_id=BROKER,
            harness_sha=HARNESS,
            caller_policy_sha256=CALLER,
            max_seconds=300,
        )
        with self.assertRaisesRegex(NotAuthorized, "PRIVATE_INTENT_ISSUE_REJECTED"):
            self.issue(policy=policy)
        self.assertEqual(self.journal.calls, 0)


if __name__ == "__main__":
    unittest.main()
