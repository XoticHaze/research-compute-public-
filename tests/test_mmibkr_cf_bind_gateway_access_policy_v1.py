import unittest
from scripts.mmibkr_cf_bind_gateway_access_policy_v1 import (
    APP_NAME, DOMAIN, HOST, POLICY_NAME, TOKEN_NAME,
    is_hex_id, approved_policy, provision,
)

ACCOUNT="a"*32
TOKEN="11111111-2222-3333-4444-555555555555"
POLICY="66666666-7777-8888-9999-aaaaaaaaaaaa"
APP="bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
CLIENT_ID="FAKE-CF-ID.access"


class FakeAPI:
    account=ACCOUNT
    def __init__(self, *, policies=None, service_name=TOKEN_NAME,
                 external_policy=False, zone_account=ACCOUNT):
        self.policies=[] if policies is None else policies
        self.service_name=service_name
        self.zone_account=zone_account
        self.app_policies=[{"id":"other-policy"}] if external_policy else []
        self.actions=[]

    def call(self, method, path, data=None):
        self.actions.append((method, path, data))
        if path.startswith("/zones?"):
            return True,200,[{"name":DOMAIN,"status":"active","account":{"id":self.zone_account}}]
        if path.endswith("/access/service_tokens?per_page=100"):
            return True,200,[{"id":TOKEN,"client_id":CLIENT_ID,"name":self.service_name,"enabled":True}]
        if path.endswith("/access/apps?per_page=100"):
            return True,200,[self.app()]
        if path.endswith("/access/policies?per_page=100"):
            return True,200,self.policies
        if method=="POST" and path.endswith("/access/policies"):
            self.policies.append({"id":POLICY,**data})
            return True,201,self.policies[-1]
        if method=="PUT" and path.endswith("/access/apps/"+APP):
            self.app_policies=data["policies"]
            return True,200,self.app()
        if method=="GET" and path.endswith("/access/apps/"+APP):
            return True,200,self.app()
        if method=="GET" and path.endswith("/access/policies/"+POLICY):
            return True,200,next(x for x in self.policies if x["id"]==POLICY)
        raise AssertionError("Unexpected call: " + method+" "+path)

    def app(self):
        return {"name":APP_NAME,"domain":HOST,"type":"self_hosted",
                "id":APP,"policies":self.app_policies}


class GatewayServiceAuthTests(unittest.TestCase):
    def test_exact_token_one_service_auth_only(self):
        api=FakeAPI()
        self.assertEqual(provision(api,CLIENT_ID,service_secret_present=True),"PASS_EXACT_SERVICE_AUTH_ONLY")
        self.assertEqual(len([a for a in api.actions if a[0]=="POST"]),1)
        p=api.policies[0]
        self.assertTrue(approved_policy(p,TOKEN))
        self.assertEqual(p["include"],[{"service_token":{"token_id":TOKEN}}])
        self.assertEqual(p["decision"],"non_identity")
        put=[x for x in api.actions if x[0]=="PUT"]
        self.assertEqual(len(put),1)
        self.assertEqual(put[0][2]["policies"],[{"id":POLICY,"account_id":ACCOUNT,"precedence":1}])
        self.assertTrue(put[0][2]["service_auth_401_redirect"])

    def test_replay_is_idempotent(self):
        api=FakeAPI(policies=[{"id":POLICY,"name":POLICY_NAME,"decision":"non_identity",
                               "include":[{"service_token":{"token_id":TOKEN}}]}])
        api.app_policies=[{"id":POLICY}]
        self.assertEqual(provision(api,CLIENT_ID,service_secret_present=True),"PASS_EXACT_SERVICE_AUTH_ONLY")
        self.assertFalse(any(a[0] in ("POST","PUT") for a in api.actions))

    def test_wrong_token_name_rejected_without_mutation(self):
        api=FakeAPI(service_name="another-service")
        self.assertEqual(provision(api,CLIENT_ID,service_secret_present=True),
                         "BLOCKED_EXPECTED_NAMED_SERVICE_TOKEN_NOT_FOUND")
        self.assertFalse(any(a[0] in ("POST","PUT") for a in api.actions))

    def test_existing_external_app_policy_rejected(self):
        api=FakeAPI(external_policy=True)
        self.assertEqual(provision(api,CLIENT_ID,service_secret_present=True),
                         "BLOCKED_EXISTING_APP_POLICIES_NOT_EXCLUSIVE")
        self.assertFalse(any(a[0]=="PUT" for a in api.actions))

    def test_exact_zone_account_authority(self):
        api=FakeAPI(zone_account="f"*32)
        self.assertEqual(provision(api,CLIENT_ID,service_secret_present=True),
                         "BLOCKED_ACTIVE_ZONE_ACCOUNT_MISMATCH")
        self.assertEqual(len(api.actions),1)

    def test_missing_secrets_never_queries(self):
        api=FakeAPI()
        self.assertEqual(provision(api,"",service_secret_present=True),
                         "BLOCKED_READER_SERVICE_TOKEN_SECRETS_MISSING")
        self.assertEqual(api.actions,[])

    def test_policy_validation_rejects_everyone_or_other_token(self):
        policy={"name":POLICY_NAME,"decision":"non_identity",
                "include":[{"any_valid_service_token":{}}]}
        self.assertFalse(approved_policy(policy,TOKEN))
        policy["include"]=[{"service_token":{"token_id":"f"*32}}]
        self.assertFalse(approved_policy(policy,TOKEN))
        policy["include"]=[{"service_token":{"token_id":TOKEN}}]
        self.assertTrue(approved_policy(policy,TOKEN))

    def test_cloudflare_id_variants(self):
        self.assertTrue(is_hex_id(ACCOUNT))
        self.assertTrue(is_hex_id(TOKEN))
        self.assertFalse(is_hex_id("bogus"))


if __name__=="__main__":
    unittest.main()
