import copy
import unittest

from scripts.reference_release_grant_v1 import (
    ExpectedGrant,
    GrantRejected,
    generate_authority_signer,
    sign_grant,
    verify_grant,
)


class ReferenceReleaseGrantTests(unittest.TestCase):
    def setUp(self):
        self.private, self.public, _ = generate_authority_signer()
        self.now = 100000
        self.grant = {
            "schema": "reference-release-grant-v1",
            "issuer": "private-authority-v1",
            "audience": "independent-release-broker-v1",
            "grant_id": "grant_0123456789abcdef",
            "run_id": "36177988341",
            "run_attempt": "1",
            "harness_sha": "1" * 40,
            "worker_key_id": "sha256:" + "2" * 64,
            "broker_key_id": "sha256:" + "3" * 64,
            "not_before": self.now,
            "admission_not_after": self.now + 300,
        }
        self.expected = ExpectedGrant(
            grant_id=self.grant["grant_id"],
            run_id=self.grant["run_id"],
            run_attempt=self.grant["run_attempt"],
            harness_sha=self.grant["harness_sha"],
            worker_key_id=self.grant["worker_key_id"],
            broker_key_id=self.grant["broker_key_id"],
        )

    def test_valid_grant(self):
        wrapper = sign_grant(self.private, self.grant)
        node = verify_grant(
            wrapper,
            authority_public_b64=self.public,
            expected=self.expected,
            now=self.now + 1,
        )
        self.assertEqual(self.grant, node)

    def test_tamper_rejected(self):
        wrapper = sign_grant(self.private, self.grant)
        changed = copy.deepcopy(wrapper)
        changed["payload_b64"] = changed["payload_b64"][:-4] + "AAAA"
        with self.assertRaises(GrantRejected):
            verify_grant(
                changed,
                authority_public_b64=self.public,
                expected=self.expected,
                now=self.now + 1,
            )

    def test_wrong_authority_key_rejected(self):
        wrapper = sign_grant(self.private, self.grant)
        _, other_public, _ = generate_authority_signer()
        with self.assertRaises(GrantRejected):
            verify_grant(
                wrapper,
                authority_public_b64=other_public,
                expected=self.expected,
                now=self.now + 1,
            )

    def test_wrong_broker_binding_rejected(self):
        wrapper = sign_grant(self.private, self.grant)
        expected = ExpectedGrant(
            **{**self.expected.__dict__, "broker_key_id": "sha256:" + "4" * 64}
        )
        with self.assertRaisesRegex(GrantRejected, "broker_key_id_mismatch"):
            verify_grant(
                wrapper,
                authority_public_b64=self.public,
                expected=expected,
                now=self.now + 1,
            )

    def test_long_admission_grant_rejected(self):
        grant = dict(self.grant)
        grant["admission_not_after"] = self.now + 5 * 3600
        wrapper = sign_grant(self.private, grant)
        with self.assertRaisesRegex(GrantRejected, "grant_ttl_too_long"):
            verify_grant(
                wrapper,
                authority_public_b64=self.public,
                expected=self.expected,
                now=self.now + 1,
            )


if __name__ == "__main__":
    unittest.main()
