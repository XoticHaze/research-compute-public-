"""Synthetic no-network tests for neutral credential custody metadata auditor."""
import unittest
from scripts import cc_neutral_credential_custody_readonly_v1 as m

class CustodyAuditTest(unittest.TestCase):
    def test_matching_secret_metadata_does_not_claim_token_value_or_runtime(self):
        paths = m.PATHS
        replies = {
            paths["store_list"]: (200, {"success":True,"result":[{"id":m.STORE}]}),
            paths["store_secret_metadata"]: (200, {"success":True,"result":[
                {"name":m.OWNER_ADMIN,"secret":"MUST_NOT_LEAK"},
                {"name":m.BROKER_SECRET,"secret":"ANOTHER_PRIVATE_VALUE"}]}),
            paths["maintainer_bindings"]:(200,{"success":True,"result":{
                "bindings":[{"name":m.BROKER_SECRET,
                             "type":"secrets_store_secret",
                             "value":"SHOULD_NOT_LEAK"}]}}),
        }
        touched = []
        def read(path):
            touched.append(path)
            return replies[path]
        receipt = m.examine(read)
        self.assertEqual(touched, list(m.PATHS.values()))
        self.assertTrue(receipt["known_store_metadata_visible"])
        self.assertTrue(receipt["owner_token_exact_named_secret_metadata_visible"])
        self.assertTrue(receipt["broker_editor_exact_named_secret_metadata_visible"])
        self.assertTrue(receipt["maintainer_broker_editor_binding_visible"])
        self.assertFalse(receipt["maintainer_owner_admin_binding_visible"])
        self.assertFalse(receipt["existing_owner_token_binding_proven"])
        self.assertFalse(receipt["existing_owner_token_executor_custody_proven"])
        self.assertFalse(receipt["existing_owner_token_secret_value_available"])
        self.assertEqual(receipt["cloudflare_mutations"],0)
        import json
        rendered=json.dumps(receipt)
        self.assertNotIn("MUST_NOT_LEAK",rendered)
        self.assertNotIn("ANOTHER_PRIVATE_VALUE",rendered)
        self.assertNotIn("SHOULD_NOT_LEAK",rendered)

    def test_all_gets_denied_cannot_prove_token_absence(self):
        receipt=m.examine(lambda path:(403,{}))
        self.assertEqual(receipt["conclusion"],
            "GATEWAY_CREDENTIAL_METADATA_SCOPE_INSUFFICIENT_OR_UNAVAILABLE")
        self.assertFalse(receipt["existing_owner_token_executor_custody_proven"])
        self.assertTrue(receipt["existing_owner_user_token_observed_in_ui"])
        self.assertFalse(receipt["known_store_metadata_visible"])
        self.assertEqual(receipt["cloudflare_mutations"],0)

    def test_visible_store_without_alias_does_not_mean_token_missing(self):
        def read(path):
            return (200, {"success":True,"result":[]})
        receipt=m.examine(read)
        self.assertFalse(receipt["owner_token_exact_named_secret_metadata_visible"])
        self.assertTrue(receipt["existing_owner_user_token_observed_in_ui"])
        self.assertFalse(receipt["existing_owner_token_executor_custody_proven"])
        self.assertIn("NOT_BEARER_OR_EXECUTOR_PROOF",receipt["conclusion"])

    def test_arbitrary_api_path_denied_before_http(self):
        with self.assertRaisesRegex(ValueError,"non_allowlisted_neutral_read"):
            m.read_only_api("fake-credential","/accounts/"+m.ACCOUNT+"/tokens")
        with self.assertRaisesRegex(ValueError,"non_allowlisted_neutral_read"):
            m.read_only_api("fake-credential","/accounts/"+m.ACCOUNT+"/workers/scripts/reference-release-broker-v1/settings")
        with self.assertRaisesRegex(ValueError,"non_allowlisted_neutral_read"):
            m.read_only_api("fake-credential","/accounts/"+m.ACCOUNT+"/workers/scripts/reference-release-maintainer-v1/deployments")

if __name__=="__main__":
    unittest.main()
