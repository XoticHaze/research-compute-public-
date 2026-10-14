import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("handoff",HERE/"scripts/mmibkr_live_admission_handoff_v1.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RUN="38322428844"
HEAD="a"*40

class LiveAdmissionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.old=module.record(RUN,HEAD)

    def accept(self,node=None):
        return module.accept(self.old if node is None else node,
                             current_run="38322429999",current_head="b"*40)

    def test_live_admission_is_reconciliation_only(self):
        a=self.accept()
        self.assertFalse(a["safe_for_new_readonly_gateway"])
        self.assertTrue(a["synthetic_cross_runner_receipt_accepted"])
        self.assertFalse(a["live_order_ownership_granted"])
        self.assertFalse(a["gateway_authentication_migration_proven"])

    def test_never_contains_live_broker_or_jts_material(self):
        self.assertEqual(set(self.old),module.ALLOWED)
        self.assertFalse(self.old["jts_included"])
        self.assertFalse(self.old["credentials_included"])
        self.assertFalse(self.old["gateway_session_persisted"])
        self.assertFalse(self.old["ready_for_order_ownership"])
        self.assertTrue(self.old["synthetic_only"])
        self.assertTrue(self.old["gateway_release_simulated"])
        for f in ("account_read_verified","positions_read_verified","open_orders_read_verified","gateway_released"):
            self.assertFalse(self.old[f],f)

    def test_unreleased_gateway_rejected(self):
        node=dict(self.old,gateway_released=True)
        with self.assertRaisesRegex(module.HandoffError,"predecessor_not_readonly_released"):
            self.accept(node)

    def test_any_live_submit_flag_rejected(self):
        for key in ("execution_owner_started","order_mutation",
                    "ready_for_order_ownership","credentials_included",
                    "gateway_session_persisted","jts_included"):
            with self.subTest(key=key):
                with self.assertRaises(module.HandoffError):
                    self.accept(dict(self.old,**{key:True}))

    def test_account_not_authenticated_rejected(self):
        for key in ("account_read_verified","positions_read_verified","open_orders_read_verified"):
            with self.subTest(key=key):
                with self.assertRaises(module.HandoffError):
                    self.accept(dict(self.old,**{key:True}))

    def test_stale_source_and_account_scope_rejected(self):
        for key,value in (("source_sha","0"*40),("image","wrong"),("mode","production_live_readonly_admission")):
            with self.subTest(key=key):
                with self.assertRaises(module.HandoffError):
                    self.accept(dict(self.old,**{key:value}))

    def test_truthy_live_claims_cannot_be_generated_by_fixture(self):
        receipt=module.record(RUN,HEAD)
        for name in ("account_read_verified","positions_read_verified",
                     "open_orders_read_verified","gateway_released",
                     "ready_for_order_ownership"):
            self.assertIs(receipt[name],False,name)
        self.assertIs(receipt["synthetic_only"],True)
        accepted=self.accept(receipt)
        self.assertIs(accepted["safe_for_new_readonly_gateway"],False)
        self.assertIs(accepted["live_order_ownership_granted"],False)

    def test_synthetic_identity_cannot_be_relabelled_as_real_admission(self):
        changes={"synthetic_only":False,"gateway_release_simulated":False,
                 "mode":"production_live_readonly_admission"}
        for field,value in changes.items():
            with self.subTest(field=field):
                with self.assertRaises(module.HandoffError):
                    self.accept(dict(self.old,**{field:value}))

    def test_same_run_not_predecessor(self):
        with self.assertRaisesRegex(module.HandoffError,"predecessor_run_not_distinct"):
            module.accept(self.old,current_run=RUN,current_head="b"*40)

    def test_unknown_extra_sensitive_fields_rejected(self):
        for name in ("account_id","live_username","live_password","positions","orders",
                     "jts_key","bearer","gateway_config"):
            with self.subTest(field=name):
                with self.assertRaisesRegex(module.HandoffError,"predecessor_receipt_not_exact"):
                    self.accept(dict(self.old,**{name:"secret"}))

    def test_required_fields_removed_rejected(self):
        node=dict(self.old)
        del node["gateway_released"]
        with self.assertRaisesRegex(module.HandoffError,"predecessor_receipt_not_exact"):
            self.accept(node)

    def test_invalid_run_and_commit_ref_rejected(self):
        for run,head in (("not_run",HEAD),(RUN,"bad"),("0",HEAD)):
            with self.subTest(run=run,head=head):
                with self.assertRaises(module.HandoffError):
                    module.record(run,head)

    def test_predecessor_receipt_can_be_json_roundtripped(self):
        a=self.accept(json.loads(json.dumps(self.old)))
        self.assertEqual(a["predecessor_run"],RUN)
        self.assertEqual(len(a["predecessor_receipt_sha256"]),64)

    def test_current_live_workflow_still_requires_manual_no_order_admission(self):
        text=(HERE/".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml").read_text()
        self.assertIn("if: github.event_name == 'workflow_dispatch'",text)
        self.assertIn("group: mmibkr-production-live-canonical-owner",text)
        self.assertIn("LIVE_WRT_NO_LIVE_ORDER_DISPATCHED=1",text)
        self.assertIn("EPHEMERAL_LIVE_BROKER_MUTATION_DISABLED=1",text)
        self.assertIn("admission_only",text)
        self.assertNotIn("placeOrder(",text.split("\n  owner:\n",1)[1])

if __name__=="__main__":
    unittest.main()
