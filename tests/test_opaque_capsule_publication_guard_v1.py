"""Public ciphertext-only publication regression using synthetic crypto."""
from __future__ import annotations
import base64
import json
import unittest
from scripts import opaque_bidirectional_capsule_v1 as m1
from scripts import opaque_bidirectional_capsule_p256_aesgcm_v1 as a1
from scripts.opaque_capsule_publication_guard_v1 import audit_bytes

class PublicationGateTests(unittest.TestCase):
    def test_real_padded_m1_and_a1_result_envelopes_are_accepted(self):
        for module in (m1, a1):
            with self.subTest(profile=module.SCHEMA):
                _, public, _ = module.generate_keypair()
                envelope = module.seal(b"synthetic-only", recipient_public_b64=public, run_id="99001", direction="result")
                self.assertTrue(audit_bytes(json.dumps(envelope).encode(), expected_direction="result"))
                self.assertFalse(audit_bytes(json.dumps(envelope).encode(), expected_direction="request"))
                for field, value in (("private_source", "no"), ("plaintext_sha256", "a" * 64),
                                     ("job", "workload"), ("authority", "fake")):
                    candidate = dict(envelope, **{field:value})
                    self.assertFalse(audit_bytes(json.dumps(candidate).encode(), expected_direction="result"))
                for field, value in (("run_id", "named-private-job"), ("ciphertext_sha256", "0"*64),
                                     ("recipient_key_id", "private:source"), ("nonce_b64", base64.b64encode(b"bad").decode()),
                                     ("ciphertext_b64", base64.b64encode(b"plaintext").decode())):
                    candidate = dict(envelope, **{field:value})
                    self.assertFalse(audit_bytes(json.dumps(candidate).encode(), expected_direction="result"))

    def test_non_json_duplicates_and_plaintext_are_rejected(self):
        for raw in (b"", b"not-json", b"{}", b"[]",
                    b'{"schema":"opaque-capsule-v1","schema":"opaque-capsule-p256-aesgcm-v1"}',
                    b"synthetic plaintext", b"x" * 2_000_001):
            self.assertFalse(audit_bytes(raw, expected_direction="result"))
        _, public, _ = m1.generate_keypair()
        env = m1.seal(b"synthetic", recipient_public_b64=public, run_id="99002", direction="result")
        self.assertFalse(audit_bytes(json.dumps(env).encode(), expected_direction="unknown"))

if __name__ == "__main__":
    unittest.main()
