from __future__ import annotations
import json
from io import StringIO
from pathlib import Path
import pandas as pd, requests
URL='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'; CUTOFF=pd.Timestamp('2015-01-01')
resp=requests.get(URL,headers={'User-Agent':'Mozilla/5.0 MarketResearchCorpusDiagnostic/1.0'},timeout=30); resp.raise_for_status()
tables=pd.read_html(StringIO(resp.text)); current=tables[0].copy()
def flatten_cols(df):
    x=df.copy()
    if isinstance(x.columns,pd.MultiIndex):
        out=[]
        for c in x.columns:
            parts=[]
            for v in c:
                s=str(v).strip()
                if s!='nan' and not s.lower().startswith('unnamed:') and s not in parts: parts.append(s)
            out.append(' '.join(parts).strip())
        x.columns=out
    else:
        x.columns=[str(c).strip() for c in x.columns]
    return x
flat=[flatten_cols(t) for t in tables]
changes=None
for t in flat[1:]:
    names=' | '.join(c.lower() for c in t.columns)
    if 'added' in names and 'removed' in names and len(t.columns)>=4:
        changes=t; break
if changes is None:
    # The page's historical-changes table has changed header markup more than once.
    # Accept only a conservative structural fallback: a non-current table with >=4
    # columns whose first column is substantially date-like. Column positions are
    # then used only for the historical membership/corpus sufficiency diagnostic.
    for t in flat[1:]:
        if len(t.columns)<4: continue
        parsed=pd.to_datetime(t.iloc[:,0],errors='coerce')
        if len(parsed) and float(parsed.notna().mean())>=0.50:
            changes=t; break
if changes is None: raise RuntimeError('no_historical_change_table_found_after_keyword_and_date_structure_checks')
cols=list(changes.columns)
date_col=next((c for c in cols if 'date' in c.lower()),cols[0])
added_col=next((c for c in cols if 'added' in c.lower() and ('ticker' in c.lower() or 'symbol' in c.lower())),cols[1])
removed_col=next((c for c in cols if 'removed' in c.lower() and ('ticker' in c.lower() or 'symbol' in c.lower())),cols[3] if len(cols)>3 else cols[-1])
changes[date_col]=pd.to_datetime(changes[date_col],errors='coerce'); ch=changes.loc[changes[date_col]>=CUTOFF].copy()
current_symbols=set(current['Symbol'].astype(str).str.replace('.','-',regex=False)); sector_map=dict(zip(current['Symbol'].astype(str).str.replace('.','-',regex=False),current['GICS Sector'].astype(str)))
removed=[str(x).replace('.','-') for x in ch[removed_col].dropna() if str(x).strip() and str(x)!='nan']
distinct_removed=sorted(set(removed)); removed_sector_known=sorted(set(distinct_removed)&set(sector_map)); removed_sector_missing=sorted(set(distinct_removed)-set(sector_map))
members=set(current_symbols); bad_events=[]
for _,row in ch.sort_values(date_col,ascending=False).iterrows():
    a=row.get(added_col); r=row.get(removed_col); a=None if pd.isna(a) else str(a).replace('.','-'); r=None if pd.isna(r) else str(r).replace('.','-')
    if a and a in members: members.remove(a)
    elif a: bad_events.append({'date':str(row[date_col].date()),'type':'added_not_in_rewind_members','symbol':a})
    if r: members.add(r)
missing_fraction=len(removed_sector_missing)/len(distinct_removed) if distinct_removed else 0.0
sufficient=(len(removed_sector_missing)==0 and len(bad_events)==0)
decision='P350_PUBLIC_PIT_SECTOR_MEMBERSHIP_SOURCE_SUFFICIENT' if sufficient else 'P350_PUBLIC_PIT_SECTOR_MEMBERSHIP_SOURCE_INSUFFICIENT'
out={'schema':'research.p350_pit_sector_membership_feasibility_r1','parent':'P330_CONSTITUENT_LEVEL_PIT_BOUNDARY','claim':'Corpus-feasibility diagnostic only: determine whether the public Wikipedia S&P 500 current-member table plus historical change log is sufficient to reconstruct point-in-time constituent AND historical GICS-sector membership from 2015 onward without survivorship leakage. This does not evaluate alpha.','source':URL,'cutoff':str(CUTOFF.date()),'http_status':resp.status_code,'selected_change_columns':cols,'date_col':date_col,'added_col':added_col,'removed_col':removed_col,'current_members':len(current_symbols),'change_rows_since_cutoff':int(len(ch)),'distinct_removed_tickers_since_cutoff':len(distinct_removed),'removed_tickers_with_sector_from_current_table':len(removed_sector_known),'removed_tickers_missing_historical_sector_identity':len(removed_sector_missing),'missing_sector_fraction_of_removed':missing_fraction,'sample_missing_sector_tickers':removed_sector_missing[:30],'membership_rewind_anomaly_count':len(bad_events),'membership_rewind_anomaly_sample':bad_events[:20],'rewound_member_count_at_oldest_change':len(members),'decision_rule':'The source is sufficient for an exact constituent-sector corpus only if every removed historical ticker has sector identity available from the same source and reverse membership reconstruction has no anomalies. Any missing historical sector identity means this source alone cannot support claim-relevant P330 constituent-level sector attribution without survivorship/representation assumptions.','decision':decision,'scientific_consequence':'If insufficient, do not manufacture or backfill historical sectors from current constituents. Require a point-in-time sector-classification source or a separately validated historical identity materializer; rotate research while that data boundary remains open.','boundaries':{'scientific_authority':True,'corpus_evidence':True,'alpha_evaluation':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p350_pit_sector_membership_feasibility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))