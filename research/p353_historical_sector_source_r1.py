from __future__ import annotations
import json
from io import StringIO
from pathlib import Path
import pandas as pd, requests
CURRENT='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
HIST='https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500'
CUTOFF=pd.Timestamp('2015-01-01')
headers={'User-Agent':'Mozilla/5.0 MarketResearchCorpusDiagnostic/1.0'}
rc=requests.get(CURRENT,headers=headers,timeout=30); rc.raise_for_status()
rh=requests.get(HIST,headers=headers,timeout=30); rh.raise_for_status()
ct=pd.read_html(StringIO(rc.text)); ht=pd.read_html(StringIO(rh.text))
cur=ct[0].copy(); current_symbols=set(cur['Symbol'].astype(str).str.replace('.','-',regex=False)); sector_map=dict(zip(cur['Symbol'].astype(str).str.replace('.','-',regex=False),cur['GICS Sector'].astype(str)))
# Historical page currently exposes one changes table with a MultiIndex header.
hist=None
for t in ht:
    if len(t.columns)<4: continue
    tmp=t.copy()
    if isinstance(tmp.columns,pd.MultiIndex): tmp.columns=[' '.join(dict.fromkeys(str(v).strip() for v in c if str(v)!='nan' and not str(v).lower().startswith('unnamed'))).strip() for c in tmp.columns]
    else: tmp.columns=[str(c).strip() for c in tmp.columns]
    names=' | '.join(c.lower() for c in tmp.columns)
    if ('added' in names and 'removed' in names) or ('effective date' in names and len(tmp.columns)>=5): hist=tmp; break
if hist is None: raise RuntimeError('historical_components_change_table_not_found')
cols=list(hist.columns)
date_col=next((c for c in cols if 'date' in c.lower()),cols[0])
added_col=next((c for c in cols if 'added' in c.lower() and ('ticker' in c.lower() or c.lower().endswith('added'))),cols[1])
removed_col=next((c for c in cols if 'removed' in c.lower() and ('ticker' in c.lower() or c.lower().endswith('removed'))),cols[3] if len(cols)>3 else cols[-1])
hist[date_col]=pd.to_datetime(hist[date_col],errors='coerce'); h=hist.loc[hist[date_col]>=CUTOFF].copy()
removed=sorted(set(str(x).replace('.','-') for x in h[removed_col].dropna() if str(x).strip() and str(x)!='nan'))
added=sorted(set(str(x).replace('.','-') for x in h[added_col].dropna() if str(x).strip() and str(x)!='nan'))
missing_removed=sorted(set(removed)-set(sector_map)); known_removed=sorted(set(removed)&set(sector_map))
# Membership can be rewound, but historical sector identity cannot be inferred from a present-day current table for removed firms.
members=set(current_symbols); anomalies=[]
for _,row in h.sort_values(date_col,ascending=False).iterrows():
    a=row.get(added_col); r=row.get(removed_col); a=None if pd.isna(a) else str(a).replace('.','-'); r=None if pd.isna(r) else str(r).replace('.','-')
    if a and a in members: members.remove(a)
    elif a: anomalies.append({'date':str(row[date_col].date()),'type':'added_not_current_during_rewind','symbol':a})
    if r: members.add(r)
missing_fraction=len(missing_removed)/len(removed) if removed else 0.0
sector_fields=[c for c in cols if 'sector' in c.lower() or 'gics' in c.lower()]
sufficient=(len(missing_removed)==0 and len(sector_fields)>0 and len(anomalies)==0)
decision='P353_PUBLIC_TWO_PAGE_PIT_SECTOR_SOURCE_SUFFICIENT' if sufficient else 'P353_PUBLIC_TWO_PAGE_PIT_SECTOR_SOURCE_INSUFFICIENT'
out={'schema':'research.p353_historical_sector_source_r1','parent':'P330_CONSTITUENT_LEVEL_PIT_BOUNDARY','claim':'Determine whether the current-components page plus its separately linked historical-components change table is sufficient by itself for exact point-in-time membership AND historical sector attribution from 2015 onward. No alpha is evaluated.','sources':{'current':CURRENT,'historical':HIST},'http_status':{'current':rc.status_code,'historical':rh.status_code},'cutoff':str(CUTOFF.date()),'historical_columns':cols,'historical_sector_fields':sector_fields,'change_rows_since_cutoff':int(len(h)),'distinct_added_tickers':len(added),'distinct_removed_tickers':len(removed),'removed_tickers_sector_known_from_current_table':len(known_removed),'removed_tickers_missing_sector_identity':len(missing_removed),'missing_removed_sector_fraction':missing_fraction,'sample_missing_removed_sector_tickers':missing_removed[:40],'membership_rewind_anomaly_count':len(anomalies),'membership_rewind_anomaly_sample':anomalies[:20],'rewound_member_count_at_oldest_change':len(members),'decision_rule':'Sufficient only if the historical table itself carries sector/GICS information, every removed ticker has sector identity, and reverse membership reconstruction has no anomalies. Present-day sector labels must not be imputed onto historical removed names.','decision':decision,'scientific_consequence':'If insufficient, membership history alone is not enough for P330 constituent-level sector claims. Preserve the industry ETF survivor; require an independently sourced point-in-time sector classification or issuer-sector history before constituent-level sector attribution. Do not manufacture historical sectors.','boundaries':{'scientific_authority':True,'corpus_evidence':True,'alpha_evaluation':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p353_historical_sector_source_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
