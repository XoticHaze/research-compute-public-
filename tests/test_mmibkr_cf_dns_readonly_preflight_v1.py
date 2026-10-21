from __future__ import annotations

import unittest

from scripts.mmibkr_cf_dns_readonly_preflight_v1 import (
    hostname, zone_for_host, parse_dns_answer, build_report, RECORD_TYPES,
)


class DomainPreflightTests(unittest.TestCase):
    def test_existing_com_apex_reserved_for_future_website(self):
        self.assertEqual(zone_for_host("gateway-ops.example.com"),"example.com")
        for bad in ("example.com","www.example.com","gateway-ops.example.co.uk",
                    "localhost","https://gateway.example.com","127.0.0.1",
                    "gw.example.com;rm -rf /","gw..example.com"):
            with self.assertRaises(ValueError,msg=bad):
                zone_for_host(bad)

    def test_no_raw_dns_values_leak_in_snapshot(self):
        item=parse_dns_answer("example.com","TXT",{
            "Status":0,"Answer":[
                {"name":"example.com.","type":16,"data":"v=spf1 SECRET_PUBLIC_DNS_VALUE"},
                {"name":"other.example.com.","type":16,"data":"irrelevant"},
            ]
        })
        self.assertEqual(item["count"],1)
        self.assertEqual(len(item["values_sha256"][0]),64)
        self.assertNotIn("SECRET_PUBLIC_DNS_VALUE",str(item))

    def test_cloudflare_nameserver_delegation_must_use_two(self):
        good=parse_dns_answer("example.com","NS",{
            "Status":0,"Answer":[
                {"name":"example.com.","type":2,"data":"adam.ns.cloudflare.com."},
                {"name":"example.com.","type":2,"data":"betty.ns.cloudflare.com."},
            ]
        })
        self.assertTrue(good["cf_delegation"])
        mixed=parse_dns_answer("example.com","NS",{
            "Status":0,"Answer":[
                {"name":"example.com.","type":2,"data":"betty.ns.cloudflare.com."},
                {"name":"example.com.","type":2,"data":"dns1.registrar.net."},
            ]
        })
        self.assertFalse(mixed["cf_delegation"])

    def test_failed_recursive_lookup_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"resolution_failed"):
            parse_dns_answer("example.com","NS",{"Status":2})
        with self.assertRaisesRegex(ValueError,"bad_doh_response"):
            parse_dns_answer("example.com","NS",None)

    def test_first_run_preserves_dnssec_mail_and_existing_subdomain(self):
        def query(name,kind):
            values=[]
            if name=="example.com" and kind=="NS":
                values=["dns1.registrar.net.","dns2.registrar.net."]
            elif name=="example.com" and kind=="DS":
                values=["12345 13 2 deadbeef"]
            elif name=="example.com" and kind=="MX":
                values=["10 mail.example.com."]
            elif name=="gateway-ops.example.com" and kind=="CNAME":
                values=["already-used.example.net."]
            return parse_dns_answer(name,kind,{
                "Status":0,
                "Answer":[{"name":name+".","type":RECORD_TYPES[kind],"data":v} for v in values],
            })
        a=build_report("gateway-ops.example.com",query=query)
        self.assertFalse(a["managed_zone_is_cloudflare"])
        self.assertTrue(a["delegation_ds_detected_by_recursive_lookup"])
        self.assertTrue(a["gateway_subdomain_already_has_records"])
        self.assertTrue(a["root_mx_records_present"])
        self.assertEqual(a["next_stage"],"REVIEW_EXISTING_GATEWAY_SUBDOMAIN")
        self.assertFalse(a["broker_connection_attempted"])

    def test_cloudflare_active_zone_with_unused_gateway_host(self):
        def query(name,kind):
            values=["adam.ns.cloudflare.com.","betty.ns.cloudflare.com."] if name=="example.com" and kind=="NS" else []
            return parse_dns_answer(name,kind,{
                "Status":0,"Answer":[{"name":name+".","type":RECORD_TYPES[kind],"data":v} for v in values]
            })
        a=build_report("gateway-ops.example.com",query=query)
        self.assertTrue(a["managed_zone_is_cloudflare"])
        self.assertFalse(a["gateway_subdomain_already_has_records"])
        self.assertEqual(a["next_stage"],"DEDICATED_ACCESS_TUNNEL_SETUP")

    def test_ns_switch_with_ds_requires_review_first(self):
        def query(name,kind):
            values=["12 13 2 beef"] if name=="example.com" and kind=="DS" else []
            return parse_dns_answer(name,kind,{
                "Status":0,"Answer":[{"name":name+".","type":RECORD_TYPES[kind],"data":v} for v in values]
            })
        a=build_report("gateway-ops.example.com",query=query)
        self.assertEqual(a["next_stage"],"REVIEW_DNSSEC_BEFORE_SWITCH")


if __name__=="__main__":
    unittest.main()
