from __future__ import annotations

import json
import unittest

from scripts.mmibkr_public_cloud_receipt_projection_v1 import project
from scripts import mmibkr_cloud_session_acceptance_v1 as acceptance
from tests.test_mmibkr_cloud_session_acceptance_v1 import MMIBKRCloudSessionAcceptanceTests


class PublicReceiptProjectionTests(unittest.TestCase):
    def _fixture(self):
        receipt = MMIBKRCloudSessionAcceptanceTests().good_receipt(restored=False)
        receipt.update({
            "status": "private failure: patient=TEST_PRIVATE_SENTINEL",
            "last_cycle": {
                "ok": True,
                "account": {"number": "TEST_PRIVATE_SENTINEL"},
                "orders": ["TEST_PRIVATE_SENTINEL"],
                "strategy": "TEST_PRIVATE_SENTINEL",
            },
            "futures_roll_maintenance": {
                "raw_contract": "TEST_PRIVATE_SENTINEL",
                "broker_session": {"token": "TEST_PRIVATE_SENTINEL"},
            },
        })
        return receipt

    def test_private_nested_data_is_absent_without_breaking_acceptance(self):
        original = self._fixture()
        self.assertTrue(acceptance.evaluate(
            original, require_checkpoint_restored=False
        )["accepted"])
        public = project(original)
        self.assertNotIn("TEST_PRIVATE_SENTINEL", json.dumps(public))
        self.assertEqual(public["last_cycle"], {"ok": True})
        self.assertEqual(public["futures_roll_maintenance"], {})
        self.assertEqual(public["status"], "accepted")
        self.assertEqual(public["checkpoint_cache_sha256"], original["checkpoint_cache_sha256"])
        self.assertEqual(public["operator_snapshot_publish"], original["operator_snapshot_publish"])
        self.assertTrue(acceptance.evaluate(
            public, require_checkpoint_restored=False
        )["accepted"])
        self.assertIn("TEST_PRIVATE_SENTINEL", json.dumps(original))

    def test_failure_preserves_safe_public_outcome_only(self):
        receipt = self._fixture()
        receipt["session_accepted"] = False
        receipt["last_cycle"] = {"ok": False, "error": "TEST_PRIVATE_SENTINEL"}
        projected = project(receipt)
        self.assertEqual(projected["status"], "not_accepted")
        self.assertEqual(projected["last_cycle"], {"ok": False})
        self.assertNotIn("TEST_PRIVATE_SENTINEL", json.dumps(projected))

    def test_extra_private_fields_fail_closed(self):
        receipt = self._fixture()
        receipt["debug_logs"] = "TEST_PRIVATE_SENTINEL"
        with self.assertRaisesRegex(ValueError, "unreviewed_fields"):
            project(receipt)

    def test_malformed_schema_and_acceptance_fail_closed(self):
        receipt = self._fixture()
        receipt["schema"] = "other"
        with self.assertRaisesRegex(ValueError, "schema_rejected"):
            project(receipt)
        receipt["schema"] = acceptance.SCHEMA
        receipt["session_accepted"] = "true"
        with self.assertRaisesRegex(ValueError, "acceptance_type_rejected"):
            project(receipt)


if __name__ == "__main__":
    unittest.main()
