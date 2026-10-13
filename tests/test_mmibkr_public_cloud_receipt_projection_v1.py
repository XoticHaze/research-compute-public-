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

    def test_allowed_nested_objects_reject_unreviewed_private_sentinel(self):
        # Existing top-level allowlisting cannot protect unbounded child dicts.
        for key in ("operator_snapshot_publish", "initial_backfill_ingest"):
            with self.subTest(key=key):
                receipt = self._fixture()
                receipt[key]["unreviewed_private_debug"] = "TEST_PRIVATE_SENTINEL"
                with self.assertRaisesRegex(ValueError, "unreviewed_nested_field"):
                    project(receipt)

    def test_nested_allowed_values_reject_private_sentinel_and_wrong_types(self):
        variants = (
            ("operator_snapshot_publish", "status", "TEST_PRIVATE_SENTINEL"),
            ("operator_snapshot_publish", "positions_count", {"private": "TEST_PRIVATE_SENTINEL"}),
            ("operator_snapshot_publish", "credentials_included", "false"),
            ("initial_backfill_ingest", "artifact_name", "TEST_PRIVATE_SENTINEL/secret.json"),
            ("initial_backfill_ingest", "public_run_id", "TEST_PRIVATE_SENTINEL"),
            ("initial_backfill_ingest", "preowner_checkpoint_cache_key", {"private": "TEST_PRIVATE_SENTINEL"}),
            ("initial_backfill_ingest", "broker_action", "false"),
        )
        for key, field, value in variants:
            with self.subTest(key=key, field=field):
                receipt = self._fixture()
                receipt[key][field] = value
                with self.assertRaisesRegex(ValueError, "nested_value"):
                    project(receipt)

    def test_workflow_failure_receipt_nullable_nested_fields_remain_publishable(self):
        # The current workflow emits None for unavailable counts, safety flags
        # and checkpoint identifiers on a failed session. Preserve that safe
        # public outcome rather than converting it to a successful receipt.
        receipt = self._fixture()
        receipt["session_accepted"] = False
        publish = receipt["operator_snapshot_publish"]
        publish.update({
            "status": "not_available_for_runtime_source",
            "runtime_count": None, "positions_count": None,
            "account_identifiers_included": None, "credentials_included": None,
            "tokens_included": None, "private_source_included": None,
            "execution_authority_included": None,
            "broker_mutation_authority": None, "live_execution_allowed": None,
        })
        backfill = receipt["initial_backfill_ingest"]
        backfill.update({
            "public_run_id": None, "amat_target_rows": None,
            "aph_target_rows": None, "mnq_source_rows": None,
            "mnq_target_rows": None, "preowner_checkpoint_sha256": None,
            "preowner_checkpoint_cache_key": None,
        })
        public = project(receipt)
        self.assertEqual(public["status"], "not_accepted")
        self.assertEqual(public["operator_snapshot_publish"], publish)
        self.assertEqual(public["initial_backfill_ingest"], backfill)

    def test_allowed_top_level_scalar_rejects_private_sentinel(self):
        variants = (
            ("source_transport", "TEST_PRIVATE_SENTINEL"),
            ("checkpoint_cache_key", "TEST_PRIVATE_SENTINEL"),
            ("private_head", "TEST_PRIVATE_SENTINEL"),
            ("run_id", "TEST_PRIVATE_SENTINEL"),
            ("cycle_count", {"private": "TEST_PRIVATE_SENTINEL"}),
        )
        for field, value in variants:
            with self.subTest(field=field):
                receipt = self._fixture()
                receipt[field] = value
                with self.assertRaisesRegex(ValueError, "scalar_"):
                    project(receipt)

    def test_allowed_nested_identity_cannot_launder_private_sentinel(self):
        variants = (
            ("artifact_name", "TEST_PRIVATE_SENTINEL"),
            ("public_run_id", "12345678901"),
            ("preowner_checkpoint_cache_key", "mmibkr-selected-runtime-cloud-checkpoint-v1-35699999999-TEST_PRIVATE_SENTINEL-initial-backfill-preowner"),
        )
        for field, value in variants:
            with self.subTest(field=field):
                receipt = self._fixture()
                receipt["initial_backfill_ingest"][field] = value
                with self.assertRaisesRegex(ValueError, "nested_identity_rejected"):
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
