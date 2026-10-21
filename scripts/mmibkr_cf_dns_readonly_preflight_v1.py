from __future__ import annotations

"""Read-only public DNS readiness audit for an existing registrar-held domain.

Queries public DNS-over-HTTPS; no Cloudflare/registrar credentials, changes,
account metadata, or trading secrets. Record values are SHA256-redacted.
This is a public-recursive view, NOT a complete registrar-zone backup.
"""

import argparse
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
KINDS = ("NS", "A", "AAAA", "CNAME", "MX", "TXT", "CAA", "DS")
RECORD_TYPES = {"A":1, "NS":2, "CNAME":5, "MX":15, "TXT":16, "AAAA":28, "DS":43, "CAA":257}
REVERSE_TYPES = {v:k for k,v in RECORD_TYPES.items()}


def hostname(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if len(value) > 253 or len(value) < 5 or not 2 <= len(value.split(".")) <= 12:
        raise ValueError("dns_audit_invalid_hostname")
    if any(not LABEL.fullmatch(x) for x in value.split(".")):
        raise ValueError("dns_audit_invalid_hostname")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("dns_audit_numeric_address_rejected")


def zone_for_host(target: str) -> str:
    # This adapter is intentionally scoped to an existing .com apex; don't
    # accidentally derive a public suffix like co.uk via naive splitting.
    name = hostname(target)
    labels = name.split(".")
    if len(labels) < 3 or labels[-1] != "com":
        raise ValueError("dns_audit_requires_subdomain_of_com")
    zone = ".".join(labels[-2:])
    if name in (zone, "www." + zone):
        raise ValueError("dns_audit_reserves_apex_and_www")
    return zone


def parse_dns_answer(name: str, kind: str, response: dict) -> dict:
    """Reduce public answers to counts and hashes; do not log DNS contents."""
    if not isinstance(response, dict):
        raise ValueError("dns_audit_bad_doh_response")
    status = response.get("Status")
    if type(status) is not int or status not in (0, 3):
        raise ValueError("dns_audit_resolution_failed")
    expected_type = RECORD_TYPES[kind]
    values = []
    for item in response.get("Answer", []) or []:
        if not isinstance(item, dict) or item.get("type") != expected_type:
            continue
        if str(item.get("name", "")).rstrip(".").lower() != name:
            continue
        v = str(item.get("data", "")).strip()
        if v:
            values.append(v)
    return {
        "name_role": kind,
        "rcode": status,
        "count": len(values),
        "values_sha256": sorted(hashlib.sha256(v.encode()).hexdigest() for v in values),
        "cf_delegation": (
            kind == "NS" and len(values) >= 2
            and all(v.lower().rstrip(".").endswith(".ns.cloudflare.com") for v in values)
        ),
    }


def query_public_resolver(name: str, kind: str, *, requester=urlopen) -> dict:
    url="https://dns.google/resolve?" + urlencode({"name":name,"type":kind})
    request=Request(url,headers={"Accept":"application/dns-json","User-Agent":"mmibkr-dns-readonly-audit-v1"})
    with requester(request,timeout=15) as resp:
        node=json.loads(resp.read(128000))
    return parse_dns_answer(name,kind,node)


def build_report(host: str, *, query=query_public_resolver) -> dict:
    zone=zone_for_host(host)
    lookups=[
        (zone,"NS"), (zone,"DS"), (zone,"MX"),
        (zone,"TXT"), (zone,"A"), (zone,"AAAA"), (zone,"CAA"),
        ("www."+zone,"A"), ("www."+zone,"CNAME"),
        ("_dmarc."+zone,"TXT"),
        (host,"CNAME"),(host,"A"),(host,"AAAA"),
    ]
    evidence=[]
    for target,kind in lookups:
        item=query(target,kind)
        evidence.append({"role": (
            "zone" if target == zone else
            "www" if target == "www."+zone else
            "dmarc" if target == "_dmarc."+zone else "gateway_subdomain"
        ),"kind":kind, **item})
    pick=lambda role,kind: next(x for x in evidence if x["role"]==role and x["kind"]==kind)
    cf=pick("zone","NS")["cf_delegation"]
    ds=pick("zone","DS")["count"]>0
    target_used=any(x["count"]>0 for x in evidence if x["role"]=="gateway_subdomain")
    return {
        "schema":"mmibkr.cloudflare_domain_dns_readonly_preflight.v1",
        "record_values_redacted":True,
        "registrar_dns_or_cloudflare_modified":False,
        "broker_connection_attempted":False,
        "managed_zone_is_cloudflare":bool(cf),
        "delegation_ds_detected_by_recursive_lookup":bool(ds),
        "gateway_subdomain_already_has_records":bool(target_used),
        "existing_root_or_www_records_present":any(
            x["count"]>0 for x in evidence if x["role"] in ("zone","www")
        ),
        "root_mx_records_present":pick("zone","MX")["count"]>0,
        "dns_record_evidence":evidence,
        "next_stage":(
            "REVIEW_EXISTING_GATEWAY_SUBDOMAIN" if target_used else
            "REVIEW_DNSSEC_BEFORE_SWITCH" if ds and not cf else
            "CLOUDFLARE_ZONE_AND_REGISTRAR_NAMESERVER_SETUP" if not cf else
            "DEDICATED_ACCESS_TUNNEL_SETUP"
        ),
        "limits":"Public recursive DNS only; registrar account, hidden/parked records and Cloudflare zone membership unverified",
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--host",required=True,help="Dedicated gateway subdomain; NOT apex/www")
    p.add_argument("--output",default="")
    a=p.parse_args()
    report=build_report(a.host)
    serialized=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if a.output:
        from pathlib import Path
        out=Path(a.output)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(serialized)
    print("MMIBKR_DOMAIN_DNS_READONLY_AUDIT=PASS")
    for key in ("managed_zone_is_cloudflare","delegation_ds_detected_by_recursive_lookup","gateway_subdomain_already_has_records","root_mx_records_present","next_stage"):
        print("MMIBKR_DNS_"+key.upper()+"="+str(report[key]))
    print("MMIBKR_DNS_RECORD_CONTENT_VALUES_LOGGED=NO")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
