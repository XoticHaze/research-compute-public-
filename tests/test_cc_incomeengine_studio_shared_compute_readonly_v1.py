import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.cc_incomeengine_studio_shared_compute_readonly_v1 import exact_readback,ZONE,HOST,OWNER_POLICY
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
            if '/access/apps?' in path:return True,200,[{'domain':HOST,'name':'IE Studio'}]
            if '/access/policies?' in path:return True,200,[{'name':OWNER_POLICY}]
            raise AssertionError(path)
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(s['studio_dns_state'],'EXACT_RECORD_PRESENT')
        self.assertEqual(s['exact_studio_access_app'],'EXACT_HOST_APP_PRESENT')
        self.assertEqual(s['owner_policy_state'],'NAMED_POLICY_VISIBLE')
        self.assertEqual(s['cloudflare_mutations'],0)
        self.assertFalse(s['homeassistant_mutated'])
        self.assertEqual(len(paths),4)
    def test_access_403_does_not_equate_to_absent_app(self):
        def read(method,path):
            if path.startswith('/zones?'):return True,200,[{'name':ZONE,'status':'active','id':'b'*32,'account':{'id':ACCOUNT}}]
            return False,403,None
        s=exact_readback(read,ACCOUNT)
        self.assertEqual(s['exact_studio_access_app'],'UNKNOWN')
        self.assertEqual(s['owner_policy_state'],'UNKNOWN')
        self.assertEqual(s['studio_dns_state'],'UNKNOWN')
if __name__=='__main__':unittest.main()