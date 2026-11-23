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
from urllib.parse import urlencode

ZONE='lifelatelycounseling.com'
HOST='studio.'+ZONE
OWNER_POLICY='IncomeEngine Studio Owner Only'


def exact_readback(read,account):
    evidence={'schema':'commandcenter.incomeengine.studio_shared_compute_zone_readonly.v1',
        'zone_get_http':None,'exact_active_zone_owner':'NOT_VERIFIED',
        'studio_dns_get_http':None,'studio_dns_state':'UNKNOWN',
        'access_apps_get_http':None,'exact_studio_access_app':'UNKNOWN',
        'studio_access_audience_metadata':'UNVERIFIED',
        'access_organization_get_http':None,
        'studio_access_team_domain_metadata':'UNVERIFIED',
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
    ok,status,organization=read('GET',f'/accounts/{account}/access/organizations')
    evidence['access_organization_get_http']=status
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
    outcome=exact_readback(api.call,account)
    print(json.dumps(outcome,sort_keys=True))
    print('IE_STUDIO_SHARED_COMPUTE_GET_ONLY=PASS')
    return 0

if __name__=='__main__':raise SystemExit(main())