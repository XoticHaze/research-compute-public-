import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.mmibkr_cf_access_existing_token_probe_v1 import (
    APP_NAME, DOMAIN, HOST, ScopedAPI, protect_gateway_deny_default,
    summarize_token,
)


def fake_api(*, zone=True, incumbent=True, collision=None, post=None):
    api=ScopedAPI("IN_MEMORY_FAKE", "a"*32)
    api.apps=([{"name":"MM-IBKR Operator Console","domain":"mmibkr-operator-console.slenderiq.workers.dev"}]
              if incumbent else [])
    if collision:
        api.apps.append(collision)
    api.zones=[{"name":DOMAIN,"status":"active","account":{"id":"a"*32}}] if zone else []
    calls=[]
    def call(method,path,data=None):
        calls.append((method,path,data))
        if post is not None:
            return post
        return True,200,{"domain":HOST,"id":"NON_SECRET_FAKE"}
    api.call=call
    return api,calls


class ExistingCloudflareTokenProbeTests(unittest.TestCase):
    def test_create_only_when_exact_active_zone_and_incumbent_authority(self):
        api,calls=fake_api()
        result=protect_gateway_deny_default(api,approved=True)
        self.assertEqual(result,"CREATED_DENY_DEFAULT_NO_SERVICE_TOKEN")
        self.assertEqual(len(calls),1)
        method,path,body=calls[0]
        self.assertEqual(method,"POST")
        self.assertEqual(path,"/accounts/"+"a"*32+"/access/apps")
        self.assertEqual(body["domain"],HOST)
        self.assertEqual(body["type"],"self_hosted")
        self.assertEqual(body["policies"],[])
        self.assertFalse(body["app_launcher_visible"])

    def test_no_mutation_when_not_approved(self):
        api,calls=fake_api()
        self.assertEqual(protect_gateway_deny_default(api,approved=False),"NOT_REQUESTED")
        self.assertEqual(calls,[])

    def test_existing_token_attempts_creation_without_unrelated_zone_permission(self):
        api,calls=fake_api(zone=False)
        self.assertEqual(protect_gateway_deny_default(api,approved=True),"CREATED_DENY_DEFAULT_NO_SERVICE_TOKEN")
        self.assertEqual(len(calls),1)

    def test_existing_token_attempts_creation_without_incumbent_read_authority(self):
        api,calls=fake_api(incumbent=False)
        self.assertEqual(protect_gateway_deny_default(api,approved=True),"CREATED_DENY_DEFAULT_NO_SERVICE_TOKEN")
        self.assertEqual(len(calls),1)

    def test_matching_existing_gateway_app_preserved(self):
        api,calls=fake_api(collision={"name":APP_NAME,"domain":HOST,"policies":[{"decision":"service_auth"}]})
        self.assertEqual(protect_gateway_deny_default(api,approved=True),"EXISTS_PRESERVED_NO_MUTATION")
        self.assertEqual(calls,[])

    def test_domain_or_name_collision_fails_closed(self):
        api,calls=fake_api(collision={"name":APP_NAME,"domain":"bad.example.com"})
        self.assertIn("BLOCKED_NONMATCHING",protect_gateway_deny_default(api,approved=True))
        self.assertEqual(calls,[])

    def test_no_token_or_id_content_printed_on_permission_failure(self):
        from urllib.error import HTTPError
        def opener(request,timeout):
            raise HTTPError(request.full_url,403,"CLOUDFLARE_SECRET_BODY",None,None)
        text=io.StringIO()
        with redirect_stdout(text):
            api=summarize_token("VERY_SECRET_TOKEN","a"*32,"LEGACY",opener=opener)
        self.assertIsNone(api.apps)
        self.assertIn("HTTP_403",text.getvalue())
        self.assertNotIn("VERY_SECRET_TOKEN",text.getvalue())
        self.assertNotIn("a"*32,text.getvalue())

    def test_access_write_denial_reported_exactly(self):
        api,calls=fake_api(post=(False,403,None))
        self.assertEqual(protect_gateway_deny_default(api,approved=True),"POST_REJECTED_HTTP_403_NO_DETAIL")
        self.assertEqual(len(calls),1)

    def test_service_token_create_never_called(self):
        api,calls=fake_api()
        protect_gateway_deny_default(api,approved=True)
        self.assertFalse(any("service_tokens" in path for _,path,_ in calls))


if __name__=="__main__":
    unittest.main()
