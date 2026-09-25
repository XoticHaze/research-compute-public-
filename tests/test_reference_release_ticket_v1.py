import copy
import unittest

from scripts.reference_release_ticket_v1 import (
    ExpectedRelease,
    TicketRejected,
    generate_signer,
    sign_ticket,
    verify_ticket,
)


class ReferenceReleaseTicketTests(unittest.TestCase):
    def setUp(self):
        self.private, self.public, _ = generate_signer()
        self.now = 100000
        self.claims = {
            "schema": "reference-release-ticket-v1",
            "issuer": "independent-release-broker-v1",
            "grant_id": "grant_0123456789abcdef",
            "run_id": "36177988341",
            "run_attempt": "1",
            "harness_sha": "1" * 40,
            "worker_key_id": "sha256:" + "2" * 64,
            "issued_at": self.now,
            "admission_not_after": self.now + 300,
        }
        self.expected = ExpectedRelease(
            grant_id=self.claims["grant_id"],
            run_id=self.claims["run_id"],
            run_attempt=self.claims["run_attempt"],
            harness_sha=self.claims["harness_sha"],
            worker_key_id=self.claims["worker_key_id"],
        )

    def test_valid_ticket(self):
        wrapper = sign_ticket(self.private, self.claims)
        node = verify_ticket(
            wrapper,
            signer_public_b64=self.public,
            expected=self.expected,
            now=self.now + 1,
        )
        self.assertEqual(self.claims, node)

    def test_tamper_rejected(self):
        wrapper = sign_ticket(self.private, self.claims)
        changed = copy.deepcopy(wrapper)
        changed["payload_b64"] = changed["payload_b64"][:-4] + "AAAA"
        with self.assertRaises(TicketRejected):
            verify_ticket(
                changed,
                signer_public_b64=self.public,
                expected=self.expected,
                now=self.now + 1,
            )

    def test_wrong_signer_rejected(self):
        wrapper = sign_ticket(self.private, self.claims)
        _, other_public, _ = generate_signer()
        with self.assertRaises(TicketRejected):
            verify_ticket(
                wrapper,
                signer_public_b64=other_public,
                expected=self.expected,
                now=self.now + 1,
            )

    def test_wrong_binding_rejected(self):
        wrapper = sign_ticket(self.private, self.claims)
        cases = [
            ("grant_id", "other_grant"),
            ("run_id", "99999"),
            ("run_attempt", "2"),
            ("harness_sha", "3" * 40),
            ("worker_key_id", "sha256:" + "4" * 64),
        ]
        for field, value in cases:
            expected = self.expected.__dict__.copy()
            expected[field] = value
            with self.assertRaises(TicketRejected):
                verify_ticket(
                    wrapper,
                    signer_public_b64=self.public,
                    expected=ExpectedRelease(**expected),
                    now=self.now + 1,
                )

    def test_expiry_rejected(self):
        wrapper = sign_ticket(self.private, self.claims)
        with self.assertRaisesRegex(TicketRejected, "ticket_expired"):
            verify_ticket(
                wrapper,
                signer_public_b64=self.public,
                expected=self.expected,
                now=self.claims["admission_not_after"],
            )

    def test_ticket_cannot_be_stretched_to_five_hour_execution(self):
        claims = dict(self.claims)
        claims["admission_not_after"] = self.now + 5 * 60 * 60
        wrapper = sign_ticket(self.private, claims)
        with self.assertRaisesRegex(TicketRejected, "ticket_ttl_too_long"):
            verify_ticket(
                wrapper,
                signer_public_b64=self.public,
                expected=self.expected,
                now=self.now + 1,
            )


if __name__ == "__main__":
    unittest.main()
