from __future__ import annotations
import hashlib, json, re, urllib.request
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pitindex

PIN='2df030e5c9be7c83cf4b28c3d8597d74d274757e'
SEC_URL='https://www.sec.gov/Archives/edgar/cik-lookup-data.txt'
OUT=Path('research/artifacts/mr_sec_cik_bridge_probe_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def norm_name(s: str) -> str:
    s=(s or '').upper().replace('&',' AND ')
    s=re.sub(r'[^A-Z0-9 ]+',' ',s)
    toks=[t for t in s.split() if t not in {'THE','INC','INCORPORATED','CORP','CORPORATION','CO','COMPANY','LTD','LIMITED','PLC','LLC'}]
    return ' '.join(toks)

# Build the claim-relevant historical missing-CIK set from many PIT snapshots.
dates=pd.date_range('2010-03-31','2026-06-30',freq='QE').strftime('%Y-%m-%d').tolist()
missing={}
for d in dates:
    df=pitindex.get_constituents(d,index='sp500')
    for _,r in df.iterrows():
        cik=r.get('cik')
        if pd.isna(cik) or str(cik).strip() in {'','nan','None'}:
            key=(str(r.get('ticker','')).strip(),str(r.get('name','')).strip())
            missing.setdefault(key,[]).append(d)

source_error=None; source_sha=None; raw=''
try:
    req=urllib.request.Request(SEC_URL,headers={'User-Agent':'OpenAI-Market-Research/1.0'})
    raw=urllib.request.urlopen(req,timeout=60).read().decode('latin-1','replace')
    source_sha=hashlib.sha256(raw.encode('latin-1','replace')).hexdigest()
except Exception as e:
    source_error=repr(e)

idx=defaultdict(set)
parsed_rows=0
if raw:
    for line in raw.splitlines():
        # SEC cumulative lookup is conventionally NAME:CIK:; split from right to tolerate colons in names.
        parts=line.rstrip().rsplit(':',2)
        if len(parts)<2: continue
        name=parts[0].strip(); cik=parts[1].strip()
        if not cik.isdigit(): continue
        n=norm_name(name)
        if n:
            idx[n].add(str(int(cik)))
            parsed_rows+=1

resolved=[]; ambiguous=[]; unresolved=[]
for (ticker,name),seen in sorted(missing.items()):
    candidates=sorted(idx.get(norm_name(name),set()))
    rec={'ticker':ticker,'name':name,'normalized_name':norm_name(name),'first_seen':min(seen),'last_seen':max(seen),'snapshot_count':len(seen),'candidate_ciks':candidates}
    if len(candidates)==1: resolved.append(rec)
    elif len(candidates)>1: ambiguous.append(rec)
    else: unresolved.append(rec)

total=len(missing)
resolved_pct=100*len(resolved)/total if total else 100.0
ambiguous_pct=100*len(ambiguous)/total if total else 0.0
bridge_ready=(source_error is None and total>0 and resolved_pct>=95.0 and ambiguous_pct<=1.0)
if source_error:
    decision='SEC_CIK_SOURCE_ACCESS_FAILURE'
elif total==0:
    decision='SEC_CIK_BRIDGE_NOT_NEEDED'
elif bridge_ready:
    decision='SEC_HISTORICAL_CIK_BRIDGE_READY'
else:
    decision='SEC_HISTORICAL_CIK_BRIDGE_PARTIAL__SECONDARY_RESOLUTION_REQUIRED'

out={
 'schema':'research.mr_sec_cik_bridge_probe_20260911_r1.v1',
 'workload_id':'MR_SEC_CIK_BRIDGE_PROBE_20260911_R1',
 'parent':'P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION',
 'claim':'Measure whether PIT S&P 500 members lacking CIK can be deterministically resolved to permanent SEC CIKs from the SEC historically cumulative company-name lookup without fuzzy or look-ahead guesses.',
 'sources':{'pitindex_repository':'arielNacamulli/pitindex','pitindex_pinned_commit':PIN,'sec_cik_lookup_url':SEC_URL,'sec_cik_lookup_sha256':source_sha,'sec_source_error':source_error},
 'contract':{'snapshot_start':'2010-03-31','snapshot_end':'2026-06-30','matching':'normalized exact company name only','fuzzy_matching_forbidden':True,'unique_resolution_required':True,'ready_min_resolved_pct':95.0,'ready_max_ambiguous_pct':1.0,'alpha_inference_forbidden':True},
 'summary':{'quarterly_snapshots':len(dates),'unique_missing_cik_members':total,'sec_lookup_rows_parsed':parsed_rows,'resolved_unique':len(resolved),'ambiguous':len(ambiguous),'unresolved':len(unresolved),'resolved_pct':resolved_pct,'ambiguous_pct':ambiguous_pct},
 'resolved':resolved,
 'ambiguous':ambiguous,
 'unresolved':unresolved,
 'decision':decision,
 'boundaries':{'scientific_authority':True,'data_representation_authority':True,'portfolio_ranking':False,'allocation_authority':False,'alpha_inference':False,'runtime':False,'broker':False,'live_trading':False}
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'unique_missing_cik_members':total,'resolved_unique':len(resolved),'ambiguous':len(ambiguous),'unresolved':len(unresolved),'resolved_pct':round(resolved_pct,3),'ambiguous_pct':round(ambiguous_pct,3),'sec_source_error':source_error,'sec_cik_lookup_sha256':source_sha},sort_keys=True))
