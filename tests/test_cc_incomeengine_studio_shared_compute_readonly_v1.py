import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.cc_incomeengine_studio_shared_compute_readonly_v1 import exact_readback,ZONE,HOST,OWNER_POLICY,edge_issuer,account_edge_issuer
ACCOUNT='a'*32
class StudioSharedComputeZoneReadOnly(unittest.TestCase):
    def test_foreign_zone_does_not_proceed(self):
        paths=[]
        def read(method,path):
            self.assertEqual(method,'GET');paths.append(path)
            return True,200,[{'name':ZONE,'status':'active','id':'b'*32,'account':{'id':'f'*32}}]
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(len(paths),1)
        self.assertEqual(s['exact_active_zone_owner'],'NOT_VERIFIED')
        self.assertEqual(s['cloudflare_mutations'],0)
    def test_valid_active_owned_zone_gets_only_exact_host_and_apps(self):
        paths=[]
        def read(method,path):
            self.assertEqual(method,'GET');paths.append(path)
            if path.startswith('/zones?'):return True,200,[{'name':ZONE,'status':'active','id':'b'*32,'account':{'id':ACCOUNT}}]
            if 'dns_records?' in path:return True,200,[{'name':HOST,'type':'CNAME'}]
            if '/access/apps?' in path:return True,200,[{'domain':HOST,'name':'IE Studio','aud':'studio-audience-001'}]
            if '/access/organizations' in path:return True,200,{'auth_domain':'neutral-team.cloudflareaccess.com'}
            if '/access/policies?' in path:return True,200,[{'name':OWNER_POLICY,'include':[{'email':{'email':'owner@example.test'}}]}]
            if path.endswith('/workers/scripts'):return True,200,[{'id':'incomeengine-3d-studio'}]
            if path.endswith('/workers/scripts/incomeengine-3d-studio/settings'):return True,200,{'name':'incomeengine-3d-studio'}
            raise AssertionError(path)
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(s['studio_dns_state'],'EXACT_RECORD_PRESENT')
        self.assertEqual(s['exact_studio_access_app'],'EXACT_HOST_APP_PRESENT')
        self.assertEqual(s['owner_policy_state'],'NAMED_POLICY_VISIBLE')
        self.assertEqual(s['cloudflare_mutations'],0)
        self.assertFalse(s['homeassistant_mutated'])
        self.assertEqual(len(paths),7)
        self.assertEqual(s['studio_access_audience_metadata'],'EXACT_APP_AUDIENCE_PRESENT')
        self.assertEqual(s['studio_access_team_domain_metadata'],'NEUTRAL_TEAM_DOMAIN_PRESENT')
        self.assertEqual(s['owner_policy_single_email_selector_metadata'],'EXACT_NAMED_POLICY_HAS_SINGLE_EMAIL_SELECTOR')
        self.assertNotIn('studio-audience-001',str(s))
        self.assertNotIn('owner@example.test',str(s))
        self.assertEqual(s['studio_worker_exists'],'EXACT_SCRIPT_SETTINGS_VISIBLE')
        self.assertEqual(s['studio_worker_settings_get_http'],200)
        self.assertFalse(s['studio_worker_write_authorized'])
    def test_zone_scoped_organization_fallback_uses_verified_zone_without_values(self):
        calls=[]
        def read(method,path):
            self.assertEqual(method,'GET');calls.append(path)
            if path.startswith('/zones?'):return True,200,[{
                'name':ZONE,'status':'active','id':'b'*32,'account':{'id':ACCOUNT}}]
            if '/dns_records?' in path:return False,403,None
            if '/access/apps?' in path:return True,200,[{
                'domain':HOST,'name':'IncomeEngine 3D Studio','aud':'audience-present-123'}]
            if path==f'/accounts/{ACCOUNT}/access/organizations':
                return False,403,None
            if path==f'/zones/{"b"*32}/access/organizations':
                return True,200,{'auth_domain':'neutral-team.cloudflareaccess.com'}
            if '/access/policies?' in path:return True,200,[{
                'name':OWNER_POLICY,'include':[{'email':{'email':'owner@example.test'}}]}]
            if '/workers/' in path:return False,403,None
            raise AssertionError(path)
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(s['access_organization_get_http'],403)
        self.assertEqual(s['zone_access_organization_get_http'],200)
        self.assertEqual(s['studio_access_team_domain_metadata'],'NEUTRAL_TEAM_DOMAIN_PRESENT')
        self.assertNotIn('neutral-team.cloudflareaccess.com',str(s))
        self.assertEqual(s['cloudflare_mutations'],0)
    def test_access_403_does_not_equate_to_absent_app(self):
        def read(method,path):
            if path.startswith('/zones?'):return True,200,[{'name':ZONE,'status':'active','id':'b'*32,'account':{'id':ACCOUNT}}]
            return False,403,None
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(s['exact_studio_access_app'],'UNKNOWN')
        self.assertEqual(s['owner_policy_state'],'UNKNOWN')
        self.assertEqual(s['studio_dns_state'],'UNKNOWN')
        self.assertEqual(s['studio_access_audience_metadata'],'UNVERIFIED')
        self.assertEqual(s['studio_access_team_domain_metadata'],'UNVERIFIED')
    def test_exact_edge_issuer_and_no_cross_host_redirect(self):
        good='https://neutral-team.cloudflareaccess.com/cdn-cgi/access/login/'+HOST
        self.assertEqual(edge_issuer(HOST,302,good),'neutral-team.cloudflareaccess.com')
        for bad in [good.replace('https:','http:'),good.replace('.com/','.com.evil/'),good.replace(HOST,'wrong.example.test')]:
            self.assertIsNone(edge_issuer(HOST,302,bad))
        self.assertIsNone(edge_issuer(HOST,200,good))
    def test_edge_fallback_same_account_fixed_sibling_and_conflict(self):
        gateway='gateway-ops.'+ZONE
        apps=[{'domain':h,'type':'self_hosted','id':'11111111-2222-4333-8444-555555555555','aud':'audience-present'} for h in [HOST,gateway,'unrelated.example.test']]
        seen=[]
        def probe(h):
            seen.append(h)
            return (302,'https://neutral-team.cloudflareaccess.com/cdn-cgi/access/login/'+h) if h==gateway else (404,None)
        self.assertEqual(account_edge_issuer(apps,probe),(True,2,False))
        self.assertEqual(seen,[HOST,gateway])
        def conflict(h):
            return 302,'https://'+('one' if h==HOST else 'two')+'.cloudflareaccess.com/cdn-cgi/access/login/'+h
        self.assertEqual(account_edge_issuer(apps,conflict),(False,2,True))
    def test_live_edge_path_does_not_repeat_denied_organization_reads(self):
        calls=[]
        def read(method,p):
            calls.append(p)
            if p.startswith('/zones?'):return True,200,[{'name':ZONE,'status':'active','id':'b'*32,'account':{'id':ACCOUNT}}]
            if '/access/apps?' in p:return True,200,[{'domain':HOST,'type':'self_hosted','id':'11111111-2222-4333-8444-555555555555','aud':'audience-present'}]
            return False,403,None
        e=exact_readback(read,ACCOUNT,lambda h:(302,'https://neutral-team.cloudflareaccess.com/cdn-cgi/access/login/'+h))
        self.assertFalse(any('/access/organizations' in p for p in calls))
        self.assertEqual(e['studio_access_team_domain_metadata'],'SAME_ACCOUNT_ACCESS_EDGE_ISSUER_PRESENT')
        self.assertNotIn('neutral-team.cloudflareaccess.com',str(e))
        self.assertEqual(e['cloudflare_mutations'],0)
if __name__=='__main__':unittest.main()