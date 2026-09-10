from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
URL='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'; CUTOFF=pd.Timestamp('2015-01-01')
tables=pd.read_html(URL); current=tables[0].copy(); changes=tables[1].copy()
# normalize the public change log, which records added/removed ticker+security but not historical GICS sector for removed names
if isinstance(changes.columns,pd.MultiIndex):
    changes.columns=[' '.join([str(x) for x in c if str(x)!='nan']).strip() for c in changes.columns]
cols={c.lower():c for c in changes.columns}
date_col=next(c for c in changes.columns if 'date' in c.lower())
added_col=next(c for c in changes.columns if 'added' in c.lower() and 'ticker' in c.lower())
removed_col=next(c for c in changes.columns if 'removed' in c.lower() and 'ticker' in c.lower())
changes[date_col]=pd.to_datetime(changes[date_col],errors='coerce'); ch=changes.loc[changes[date_col]>=CUTOFF].copy()
current_symbols=set(current['Symbol'].astype(str).str.replace('.','-',regex=False)); sector_map=dict(zip(current['Symbol'].astype(str).str.replace('.','-',regex=False),current['GICS Sector'].astype(str)))
removed=[str(x).replace('.','-') for x in ch[removed_col].dropna() if str(x).strip() and str(x)!='nan']; added=[str(x).replace('.','-') for x in ch[added_col].dropna() if str(x).strip() and str(x)!='nan']
distinct_removed=sorted(set(removed)); removed_sector_known=sorted(set(distinct_removed)&set(sector_map)); removed_sector_missing=sorted(set(distinct_removed)-set(sector_map))
# Reverse the change log to test whether membership identities themselves can be reconstructed from current membership.
members=set(current_symbols); snapshots={}; bad_events=[]
for _,row in ch.sort_values(date_col,ascending=False).iterrows():
    a=row.get(added_col); r=row.get(removed_col); a=None if pd.isna(a) else str(a).replace('.','-'); r=None if pd.isna(r) else str(r).replace('.','-')
    if a and a in members: members.remove(a)
    elif a: bad_events.append({'date':str(row[date_col].date()),'type':'added_not_in_rewind_members','symbol':a})
    if r: members.add(r)
    snapshots[str(row[date_col].date())]=len(members)
# Exact constituent-level sector momentum requires each historical member to have contemporaneous sector identity; the source has no removed-name GICS column.
missing_fraction=len(removed_sector_missing)/len(distinct_removed) if distinct_removed else 0.0
sufficient=(len(removed_sector_missing)==0 and len(bad_events)==0)
decision='P350_PUBLIC_PIT_SECTOR_MEMBERSHIP_SOURCE_SUFFICIENT' if sufficient else 'P350_PUBLIC_PIT_SECTOR_MEMBERSHIP_SOURCE_INSUFFICIENT'
out={'schema':'research.p350_pit_sector_membership_feasibility_r1','parent':'P330_CONSTITUENT_LEVEL_PIT_BOUNDARY','claim':'Corpus-feasibility diagnostic only: determine whether the public Wikipedia S&P 500 current-member table plus historical change log is sufficient to reconstruct point-in-time constituent AND historical GICS-sector membership from 2015 onward without survivorship leakage. This does not evaluate alpha.','source':URL,'cutoff':str(CUTOFF.date()),'current_members':len(current_symbols),'change_rows_since_cutoff':int(len(ch)),'distinct_removed_tickers_since_cutoff':len(distinct_removed),'removed_tickers_with_sector_from_current_table':len(removed_sector_known),'removed_tickers_missing_historical_sector_identity':len(removed_sector_missing),'missing_sector_fraction_of_removed':missing_fraction,'sample_missing_sector_tickers':removed_sector_missing[:30],'membership_rewind_anomaly_count':len(bad_events),'membership_rewind_anomaly_sample':bad_events[:20],'rewound_member_count_at_oldest_change':len(members),'decision_rule':'The source is sufficient for an exact constituent-sector corpus only if every removed historical ticker has sector identity available from the same source and reverse membership reconstruction has no anomalies. Any missing historical sector identity means this source alone cannot support claim-relevant P330 constituent-level sector attribution without survivorship/representation assumptions.','decision':decision,'scientific_consequence':'If insufficient, do not manufacture or backfill historical sectors from current constituents. Require a point-in-time sector-classification source or a separately validated historical identity materializer; rotate research while that data boundary remains open.','boundaries':{'scientific_authority':True,'corpus_evidence':True,'alpha_evaluation':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p350_pit_sector_membership_feasibility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))