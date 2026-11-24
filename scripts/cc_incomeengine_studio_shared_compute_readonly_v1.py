#!/usr/bin/env python3
"""IncomeEngine Studio EXACT Shared Compute zone readback. GET only, no secrets exported.

Runs in existing CommandCenter public read-only identity-scope job with the
existing Shared Compute gateway-zone credentials, not SlenderIQ/neutral tokens.
Does NOT configure Studio, HA, Gateway, Access, DNS, tokens or billable resources.
"""
from __future__ import annotations
import json
import os
import re
from urllib.parse import urlencode,urlsplit

ZONE='lifelatelycounseling.com'
HOST='studio.'+ZONE
OWNER_POLICY='IncomeEngine Studio Owner Only'



# Fixed, previously inventoried owner hosts. Only an exact app in the
# authenticated account inventory may become an edge candidate.
EDGE_HOSTS=(HOST,'gateway-ops.'+ZONE,'ha.'+ZONE)

def edge_issuer(host,status,location):
    if host not in EDGE_HOSTS or status not in (301,302,303,307,308) or not isinstance(location,str) or len(location)>16384:
        return None
    try:
        u=urlsplit(location)
        if (u.scheme=='https' and not u.username and not u.password and not u.port
            and re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com',u.hostname or '')
            and u.path=='/cdn-cgi/access/login/'+host):
            return u.hostname
    except ValueError:
        pass
    return None

def edge_read(host):
    # Unauthenticated edge only: never pass account API bearer or follow Location.
    import urllib.request
    import urllib.error
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    if host not in EDGE_HOSTS:
        raise ValueError('not allowed')
    opener=urllib.request.build_opener(NoRedirect)
    request=urllib.request.Request('https://'+host+'/',headers={'User-Agent':'cc-studio-edge-readonly/1'})
    try:
        with opener.open(request,timeout=8) as response:
            return response.status,response.headers.get('Location')
    except urllib.error.HTTPError as e:
        return e.code,e.headers.get('Location')

def account_edge_issuer(apps,read_edge):
    observed=set()
    checked=0
    for host in EDGE_HOSTS:
        matches=[a for a in apps if isinstance(a,dict) and a.get('type')=='self_hosted'
                 and (a.get('domain')==host or host in (a.get('self_hosted_domains') or []))
                 and re.fullmatch(r'[0-9a-fA-F-]{36}',str(a.get('id') or ''))
                 and isinstance(a.get('aud'),str) and len(a['aud'])>=8]
        if len(matches)!=1:
            continue
        checked+=1
        try:
            status,location=read_edge(host)
            issuer=edge_issuer(host,status,location)
            if issuer:observed.add(issuer)
        except Exception:
            pass
    return len(observed)==1,checked,len(observed)>1


def exact_readback(read,account,read_edge=None):
    evidence={'schema':'commandcenter.incomeengine.studio_shared_compute_zone_readonly.v1',
        'zone_get_http':None,'exact_active_zone_owner':'NOT_VERIFIED',
        'studio_dns_get_http':None,'studio_dns_state':'UNKNOWN',
        'access_apps_get_http':None,'exact_studio_access_app':'UNKNOWN',
        'studio_access_audience_metadata':'UNVERIFIED',
        'access_organization_get_http':None,
        'zone_access_organization_get_http':None,
        'studio_access_team_domain_metadata':'UNVERIFIED',
        'access_edge_hosts_checked':0,'access_edge_issuer_conflict':False,
        'owner_policy_single_email_selector_metadata':'UNVERIFIED',
        'owner_policy_get_http':None,'owner_policy_state':'UNKNOWN',
        'private_data_exported':False,'credential_values_exported':False,
        'hosted_deployed':False,'cloudflare_mutations':0,
        'studio_deployment_admitted':False,'homeassistant_mutated':False,
        'workers_scripts_list_get_http':None,
        'studio_worker_settings_get_http':None,
        'studio_worker_exists':'UNKNOWN',
        'studio_worker_write_authorized':False}
    ok,status,zones=read('GET','/zones?'+urlencode({'name':ZONE,'per_page':50}))
    evidence['zone_get_http']=status
    if not ok or not isinstance(zones,list):return evidence
    exact=[z for z in zones if isinstance(z,dict) and z.get('name')==ZONE
        and z.get('status')=='active' and (z.get('account') or {}).get('id')==account
        and re.fullmatch('[0-9a-f]{32}',str(z.get('id') or ''))]
    if len(exact)!=1:return evidence
    zid=exact[0]['id']
    evidence['exact_active_zone_owner']='VERIFIED_SHARED_COMPUTE_CREDENTIAL'
    ok,status,dns=read('GET',f'/zones/{zid}/dns_records?'+urlencode({'name':HOST,'per_page':100}))
    evidence['studio_dns_get_http']=status
    if ok and isinstance(dns,list):
        evidence['studio_dns_state']='EXACT_RECORD_PRESENT' if any(isinstance(r,dict) and r.get('name')==HOST for r in dns) else 'NO_EXACT_RECORD_VISIBLE'
    ok,status,apps=read('GET',f'/accounts/{account}/access/apps?per_page=100')
    evidence['access_apps_get_http']=status
    if ok and isinstance(apps,list):
        matched=[a for a in apps if isinstance(a,dict) and (a.get('domain')==HOST or HOST in (a.get('self_hosted_domains') or []))]
        evidence['exact_studio_access_app']='EXACT_HOST_APP_PRESENT' if len(matched)==1 else 'NO_UNIQUE_STUDIO_APP_VISIBLE'
        # Presence only. Never emit AUD, identities or team domain on public runners.
        if len(matched)==1:
            aud=matched[0].get('aud')
            evidence['studio_access_audience_metadata']=(
                'EXACT_APP_AUDIENCE_PRESENT' if isinstance(aud,str) and 8<=len(aud)<=512
                else 'EXACT_APP_AUDIENCE_ABSENT_OR_INVALID')
    # The two organization endpoints already returned 403. Live successor
    # attempts the distinct edge mechanism only, not another denied API read.
    if read_edge is not None:
        if evidence['exact_studio_access_app']=='EXACT_HOST_APP_PRESENT':
            proven,checked,conflict=account_edge_issuer(apps,read_edge)
            evidence['access_edge_hosts_checked']=checked
            evidence['access_edge_issuer_conflict']=conflict
            if proven:
                evidence['studio_access_team_domain_metadata']='SAME_ACCOUNT_ACCESS_EDGE_ISSUER_PRESENT'
    else:
        ok,status,organization=read('GET',f'/accounts/{account}/access/organizations')
        evidence['access_organization_get_http']=status
        # Account GET may be 403 for zone-limited Cloudflare credentials.
        # The same endpoint also accepts the already-verified active zone ID.
        # Do not expand token scope or confuse scope denial with missing data.
        if not ok or not isinstance(organization,dict):
            zok,zstatus,zorganization=read('GET',f'/zones/{zid}/access/organizations')
            evidence['zone_access_organization_get_http']=zstatus
            if zok and isinstance(zorganization,dict):
                organization=zorganization
                ok=True
        if ok and isinstance(organization,dict):
            auth_domain=organization.get('auth_domain')
            evidence['studio_access_team_domain_metadata']=(
                'NEUTRAL_TEAM_DOMAIN_PRESENT'
                if isinstance(auth_domain,str) and bool(re.fullmatch(
                    r'[a-z0-9.-]+\.cloudflareaccess\.com',auth_domain)) and len(auth_domain)<=253
                else 'NEUTRAL_TEAM_DOMAIN_ABSENT_OR_INVALID')
    ok,status,policies=read('GET',f'/accounts/{account}/access/policies?per_page=100')
    evidence['owner_policy_get_http']=status
    if ok and isinstance(policies,list):
        exact=[p for p in policies if isinstance(p,dict) and p.get('name')==OWNER_POLICY]
        evidence['owner_policy_state']='NAMED_POLICY_VISIBLE' if len(exact)==1 else 'NOT_UNIQUE_OR_ABSENT'
        if len(exact)==1:
            policy=exact[0]
            include=policy.get('include')
            has_email=(isinstance(include,list) and len(include)==1
                and isinstance(include[0],dict)
                and isinstance(include[0].get('email'),dict)
                and isinstance(include[0]['email'].get('email'),str)
                and bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',
                    include[0]['email']['email'])))
            evidence['owner_policy_single_email_selector_metadata']=(
                'EXACT_NAMED_POLICY_HAS_SINGLE_EMAIL_SELECTOR'
                if has_email else 'OWNER_SELECTOR_NOT_VERIFIED')
    # Independent exact-name Workers GETs only. Read status never grants write.
    ok,status,scripts=read('GET',f'/accounts/{account}/workers/scripts')
    evidence['workers_scripts_list_get_http']=status
    if ok and isinstance(scripts,list):
        matched=[s for s in scripts if isinstance(s,dict) and s.get('id')=='incomeengine-3d-studio']
        evidence['studio_worker_exists']='EXACT_SCRIPT_LISTED' if len(matched)==1 else 'NOT_IN_RETURNED_LIST'
    ok,status,settings=read('GET',f'/accounts/{account}/workers/scripts/incomeengine-3d-studio/settings')
    evidence['studio_worker_settings_get_http']=status
    if ok and isinstance(settings,dict):
        evidence['studio_worker_exists']='EXACT_SCRIPT_SETTINGS_VISIBLE'
    # Never infer edit/deploy authority from GET 200 or deny from GET 403.
    return evidence


def main():
    account=os.getenv('CLOUDFLARE_GATEWAY_ACCOUNT_ID','').strip().lower()
    token=os.getenv('CLOUDFLARE_GATEWAY_ACCESS_TOKEN','').strip()
    if not re.fullmatch('[0-9a-f]{32}',account) or len(token)<20:
        print('IE_STUDIO_SHARED_COMPUTE_EXISTING_ZONE_IDENTITY=NOT_CONFIGURED')
        return 45
    from scripts.mmibkr_cf_access_existing_token_probe_v1 import ScopedAPI
    api=ScopedAPI(token,account)
    outcome=exact_readback(api.call,account,edge_read)
    print(json.dumps(outcome,sort_keys=True))
    print('IE_STUDIO_SHARED_COMPUTE_GET_ONLY=PASS')
    return 0

if __name__=='__main__':raise SystemExit(main())