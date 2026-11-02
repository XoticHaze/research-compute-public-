"""Synthetic semantic-key and no-value public audit tests."""
from __future__ import annotations
import json
import unittest
from scripts.opaque_public_tip_full_scan_v1 import classify

class FullTipAuditTests(unittest.TestCase):
    def test_canonical_envelope_shape_does_not_expose_semantic_keys(self):
        obj={"schema":"opaque-capsule-p256-aesgcm-v1","run_id":"100","direction":"result",
             "recipient_key_id":"sha256:"+"a"*64,"sender_public_b64":"synthetic",
             "nonce_b64":"synthetic","ciphertext_b64":"synthetic","ciphertext_sha256":"b"*64}
        n=classify("synthetic.json",json.dumps(obj).encode())
        self.assertEqual(n.get("canonical_outer_shape"),1)
        self.assertEqual(n.get("forbidden_outer_keys"),None)
    def test_legacy_outer_and_nested_metadata_are_counted_not_disclosed(self):
        value={"authority":"SENSITIVE_CANARY_VALUE_SHOULD_NOT_PRINT",
               "payload":{"source_repo":"PRIVATE_CANARY","x":["test"]},
               "plaintext_sha256":"0"*64}
        n=classify("synthetic.json",json.dumps(value).encode())
        self.assertEqual(n.get("forbidden_outer_keys"),1)
        self.assertEqual(n.get("forbidden_nested_keys"),1)
        self.assertNotIn("CANARY",json.dumps(n))
    def test_bad_json_and_binary_not_certified(self):
        self.assertEqual(classify("a.json",b"{no"),{"json_extension":1,"json_parse_or_duplicate_failure":1})
        self.assertEqual(classify("a.bin",b"DATA"),{"non_json_extension":1})
        self.assertEqual(classify("a.json",b'{"a":1,"a":2}')["json_parse_or_duplicate_failure"],1)

if __name__=="__main__":
    unittest.main()
