"""Public offline contract: fixed read-only live-Pi binding projection, no values."""
import importlib.util
import pathlib
import unittest

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


if __name__=="__main__":
    unittest.main()
