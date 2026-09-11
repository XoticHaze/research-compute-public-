from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd
import pitindex

PIN='2df030e5c9be7c83cf4b28c3d8597d74d274757e'
OUT=Path('research/artifacts/mr_pit_membership_probe_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
# Quarterly dates deliberately start well after the documented 2005 coverage floor.
dates=pd.date_range('2010-03-31','2026-06-30',freq='QE').strftime('%Y-%m-%d').tolist()
rows=[]; canonical=[]; errors=[]
for d in dates:
    try:
        a=pitindex.get_constituents(d,index='sp500').copy()
        b=pitindex.get_constituents(d,index='sp500').copy()
        cols=['ticker','name','cik']
        a=a[cols].sort_values(['ticker','name'],na_position='last').reset_index(drop=True)
        b=b[cols].sort_values(['ticker','name'],na_position='last').reset_index(drop=True)
        deterministic=bool(a.equals(b))
        n=len(a); dup=int(a['ticker'].duplicated().sum())
        missing_cik=int(a['cik'].isna().sum() + (a['cik'].astype(str).str.strip().isin(['','nan','None']).sum() - a['cik'].isna().sum()))
        missing_name=int(a['name'].isna().sum())
        payload=a.fillna('').astype(str).to_csv(index=False)
        h=hashlib.sha256(payload.encode()).hexdigest()
        canonical.append((d,h,payload))
        rows.append({'as_of':d,'members':n,'duplicate_tickers':dup,'missing_cik':missing_cik,'missing_cik_pct':100*missing_cik/n if n else 100.0,'missing_name':missing_name,'deterministic':deterministic,'snapshot_sha256':h})
    except Exception as e:
        errors.append({'as_of':d,'error':repr(e)})

# Sparse event history is a second authority check: there must be real membership churn.
hist=pitindex.get_constituents_history('2010-01-01','2026-06-30',index='sp500')
change_dates=int(hist['as_of'].nunique()) if 'as_of' in hist.columns else 0
info=pitindex.info(index='sp500')
all_payload=''.join(d+'\n'+h+'\n'+p for d,h,p in canonical)
authority_sha=hashlib.sha256(all_payload.encode()).hexdigest()
min_members=min((r['members'] for r in rows),default=0); max_members=max((r['members'] for r in rows),default=0)
max_missing=max((r['missing_cik_pct'] for r in rows),default=100.0)
weighted_missing=sum(r['missing_cik'] for r in rows); weighted_n=sum(r['members'] for r in rows)
weighted_missing_pct=100*weighted_missing/weighted_n if weighted_n else 100.0
membership_ready=(not errors and bool(rows) and min_members>=480 and max_members<=510 and all(r['duplicate_tickers']==0 and r['deterministic'] for r in rows) and change_dates>=20)
# Claim-relevant SEC selector cannot silently exclude a material share of the PIT universe.
sec_join_identifier_ready=membership_ready and max_missing<=1.0 and weighted_missing_pct<=0.5
if not membership_ready:
    decision='PIT_MEMBERSHIP_AUTHORITY_NOT_READY'
elif sec_join_identifier_ready:
    decision='PIT_MEMBERSHIP_AND_SEC_IDENTIFIER_BRIDGE_READY'
else:
    decision='PIT_MEMBERSHIP_READY__SEC_HISTORICAL_CIK_BRIDGE_REQUIRED'
out={
 'schema':'research.mr_pit_membership_probe_20260911_r1.v1',
 'workload_id':'MR_PIT_MEMBERSHIP_PROBE_20260911_R1',
 'parent':'P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION',
 'source':{'repository':'arielNacamulli/pitindex','pinned_commit':PIN,'package_info':info},
 'claim':'Challenge the prior P388 historical-membership blocker using an immutable public PIT membership source, while separately measuring whether historical CIK coverage is sufficient for a causal SEC CompanyFacts join.',
 'probe_contract':{'index':'sp500','quarterly_snapshots_start':'2010-03-31','quarterly_snapshots_end':'2026-06-30','member_count_band':[480,510],'duplicate_tickers_required':0,'deterministic_required':True,'minimum_change_dates':20,'sec_join_max_single_snapshot_missing_cik_pct':1.0,'sec_join_max_weighted_missing_cik_pct':0.5,'alpha_inference_forbidden':True},
 'snapshots':rows,'errors':errors,'change_dates':change_dates,'membership_authority_sha256':authority_sha,
 'summary':{'snapshots':len(rows),'min_members':min_members,'max_members':max_members,'max_missing_cik_pct':max_missing,'weighted_missing_cik_pct':weighted_missing_pct,'membership_ready':membership_ready,'sec_join_identifier_ready':sec_join_identifier_ready},
 'decision':decision,
 'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'alpha_inference':False,'runtime':False,'broker':False,'live_trading':False}
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,default=str,allow_nan=False))
print(json.dumps({'decision':decision,'snapshots':len(rows),'change_dates':change_dates,'member_range':[min_members,max_members],'max_missing_cik_pct':round(max_missing,3),'weighted_missing_cik_pct':round(weighted_missing_pct,3),'membership_authority_sha256':authority_sha,'errors':len(errors)},sort_keys=True))
