import importlib.util
from pathlib import Path
import unittest

src=Path(__file__).resolve().parents[1]/"scripts"/"anonymous_access_probe.py"
spec=importlib.util.spec_from_file_location("anonymous_access_probe",src)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class AnonymousAccessProbeSafety(unittest.TestCase):
    def test_cloudflare_access_redirect_accepted(self):
        url="https://cc-ordinary-deployments.cloudflareaccess.com/cdn-cgi/access/login/abc?opaque=sensitive"
        self.assertEqual(probe.classify(302,url),"ACCESS_LOGIN_REDIRECT_VERIFIED")
    def test_proof_same_host_access_redirect_accepted(self):
        url=probe.PROOF_ROOT+"cdn-cgi/access/login/abc"
        self.assertEqual(probe.classify(302,url),"ACCESS_LOGIN_REDIRECT_VERIFIED")
    def test_unadmitted_target_rejected_before_network(self):
        with self.assertRaises(ValueError):
            probe.probe("https://example.org/")
    def test_direct_factory_status_is_failure(self):
        body=b'{"schema":"commandcenter.cloudflare.factory_status.v1","admitted":false}'
        self.assertEqual(probe.classify(200,body=body),
                         "FAIL_OWNER_STATUS_ANONYMOUSLY_REACHABLE")
    def test_generic_403_is_not_overclaimed(self):
        self.assertEqual(probe.classify(403,body=b'Generic forbidden'),
                         "DENIAL_UNCLASSIFIED")
    def test_unrelated_redirect_is_not_trusted(self):
        self.assertEqual(probe.classify(302,"https://example.org/redirect"),
                         "REDIRECT_UNCLASSIFIED")
    def test_verified_access_deny_html_is_accepted(self):
        self.assertEqual(probe.classify(403,body=b'<h1>Cloudflare Access</h1> Denied'),
                         "ACCESS_DENIAL_PAGE_VERIFIED")

if __name__=="__main__":
    unittest.main()
