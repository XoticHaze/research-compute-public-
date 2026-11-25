"""Public offline contract: fixed read-only live-Pi binding projection, no values."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "mmibkr_pi_operator_live_bindings_readonly",
    ROOT/"scripts/mmibkr_pi_operator_live_bindings_readonly.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LivePiBindingsContract(unittest.TestCase):
    def test_value_and_account_secrets_never_leave_projection(self):
        x={"success":True,"result":{"bindings":[
            {"name":"PI_LIVE_FINANCE_HMAC_KEY","type":"secret_text",
             "text":"topsecret-should-never-appear"},
            {"name":"PI_LIVE_EXPECTED_ACCOUNT_SHA256","type":"plain_text",
             "text":"hidden-account-identity"},
            {"name":"OPERATOR_STATE","type":"durable_object_namespace",
             "id":"hidden-durable-object-namespace"},
            {"name":"PI_LIVE_FINANCE_INGEST_ENABLED","type":"plain_text","text":"1"},
            {"name":"PI_LIVE_FINANCE_ORIGIN_ADMITTED","type":"plain_text","text":"0"},
        ]}}
        r=mod.summarize_bindings(x)
        self.assertTrue(r["settings_valid"])
        self.assertEqual(r["finance_flags"]["PI_LIVE_FINANCE_INGEST_ENABLED"],"1")
        self.assertEqual(r["finance_flags"]["PI_LIVE_FINANCE_ORIGIN_ADMITTED"],"0")
        self.assertFalse(r["private_finance_origin_admitted"])
        self.assertTrue(r["bindings"]["OPERATOR_STATE"])
        for value in ("topsecret-should-never-appear","hidden-account-identity",
                      "hidden-durable-object-namespace"):
            self.assertNotIn(value,str(r))
        self.assertFalse(r["real_pi_data_served_verified"])

    def test_invalid_settings_are_not_real_pi_data(self):
        r=mod.summarize_bindings({"success":False,"result":{
            "bindings":[{"name":"PI_LIVE_FINANCE_INGEST_ENABLED","text":"1"}]}})
        self.assertFalse(r["settings_valid"])
        self.assertFalse(r["private_finance_origin_admitted"])

    def test_values_other_than_boolean_flags_not_exported(self):
        x={"success":True,"result":{"bindings":[
            {"name":"PI_LIVE_FINANCE_ORIGIN_ADMITTED","type":"plain_text",
             "text":"123-myprivatevalue"},
        ]}}
        out=mod.summarize_bindings(x)
        self.assertEqual(out["finance_flags"]["PI_LIVE_FINANCE_ORIGIN_ADMITTED"],"UNVERIFIED")
        self.assertNotIn("123-myprivatevalue",str(out))

    def test_exact_machine_policy_is_metadata_only(self):
        aid = "f174e90a-fafe-4643-bbbc-4a0ed4fc8415"
        tid = "0f74e90a-fafe-4643-bbbc-4a0ed4fc8415"
        app = {"type":"self_hosted", "id":aid, "aud":"a"*64,
               "destinations":[{"type":"public","uri":mod.FINANCE_PATH}],
               "service_auth_401_redirect":True}
        human = {"type":"self_hosted","aud":"b"*64,"domain":mod.OPERATOR_HOST}
        policy = {"decision":"non_identity","include":[{"service_token":{"token_id":tid}}]}
        with patch.object(mod, "access_pages", side_effect=[(200,[app,human],True),
                                                            (200,[policy],True)]), \
             patch.object(mod, "access_get", return_value=(200,{"success":True,"result":{
                 "id":tid,"enabled":True,"expires_at":"2099-01-01T00:00:00Z",
                 "client_id":"hidden-client-id","client_secret":"should-never-escape"}})):
            out = mod.inspect_finance_access(mod.ORIGINAL_ACCOUNT, "not-a-real-token")
        self.assertTrue(out["exact_single_service_token_policy"])
        self.assertTrue(out["distinct_machine_audience"])
        self.assertTrue(out["linked_service_token_enabled_unexpired"])
        self.assertFalse(out["root_secret_custody_verified"])
        self.assertFalse(out["machine_post_verified"])
        for secret in (aid, tid, "a"*64, "b"*64, "hidden-client-id", "should-never-escape"):
            self.assertNotIn(secret, str(out))

    def test_incomplete_inventory_never_claims_absence_and_bypass_not_accepted(self):
        with patch.object(mod, "access_pages", return_value=(403,[],False)):
            out = mod.inspect_finance_access(mod.ORIGINAL_ACCOUNT, "not-a-real-token")
        self.assertIsNone(out["exact_finance_app_count"])
        self.assertFalse(out["complete_app_inventory"])
        self.assertIsNone(mod.exact_token_policy([{"decision":"bypass","include":[{}]}]))
        self.assertIsNone(mod.exact_token_policy([{"decision":"non_identity",
                                                  "include":[{"any_valid_service_token":{}}]}]))


if __name__=="__main__":
    unittest.main()
