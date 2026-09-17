from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import pitindex

DATES=['2010-12-31','2015-12-31','2020-12-31','2025-12-31']
h=pitindex.get_constituents_history('2010-01-01','2025-12-31',index='sp500').copy()
if 'cik' not in h.columns: raise SystemExit('SOURCE_FAILURE_NO_CIK_COLUMN')

def norm_ticker(x):
    if x is None: return None
    s=str(x).strip().upper().replace('.','-')
    return s if s and s not in {'NAN','NONE','<NA>'} else None

def norm_cik(x):
    if x is None or pd.isna(x): return None
    s=str(x).strip()
    if not s or s in {'nan','None','<NA>'}: return None
    try: return str(int(float(s)))
    except Exception: return s.lstrip('0') or '0'

h['ticker_norm']=h['ticker'].map(norm_ticker)
h['cik_norm']=h['cik'].map(norm_cik)
# Identity-only recovery rule: a ticker may receive a source-native CIK only when
# the pinned PIT source associates that ticker with exactly one non-null CIK
# anywhere in the fixed history. Ambiguous/reused tickers are never filled.
pairs=h.dropna(subset=['ticker_norm','cik_norm'])[['ticker_norm','cik_norm']].drop_duplicates()
counts=pairs.groupby('ticker_norm')['cik_norm'].nunique()
unambiguous=set(counts[counts==1].index)
ambiguous=set(counts[counts>1].index)
lookup=(pairs[pairs.ticker_norm.isin(unambiguous)]
        .drop_duplicates('ticker_norm').set_index('ticker_norm')['cik_norm'].to_dict())

rows=[]
for d in DATES:
    df=pitindex.get_constituents(d,index='sp500').copy()
    df['ticker_norm']=df['ticker'].map(norm_ticker)
    df['cik_norm']=df['cik'].map(norm_cik) if 'cik' in df.columns else None
    n=len(df)
    direct=int(df.cik_norm.notna().sum())
    recoverable=df.cik_norm.isna() & df.ticker_norm.isin(lookup)
    recovered=int(recoverable.sum())
    unresolved=n-direct-recovered
    ambiguous_missing=int((df.cik_norm.isna() & df.ticker_norm.isin(ambiguous)).sum())
    final_cov=(direct+recovered)/n if n else 0.0
    rows.append({'as_of':d,'members':n,'direct_cik':direct,'source_native_recovered':recovered,'ambiguous_missing':ambiguous_missing,'unresolved':unresolved,'final_cik_coverage':final_cov})

all_hist_tickers=set(x for x in h.ticker_norm.dropna().unique())
resolved_hist=set(lookup) | set(pairs.ticker_norm)
hist_resolved=len(all_hist_tickers & resolved_hist)
hist_cov=hist_resolved/len(all_hist_tickers) if all_hist_tickers else 0.0
ambig_frac=len(ambiguous)/len(all_hist_tickers) if all_hist_tickers else 0.0
min_snap=min(r['final_cik_coverage'] for r in rows)
pass_gate=min_snap>=0.95 and hist_cov>=0.90 and ambig_frac<=0.01
out={'schema':'research.p408_pit_native_cik_lineage.v1','workload_id':'P408_PIT_NATIVE_CIK_LINEAGE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','source':'pitindex','source_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','claim':'P404 missing historical issuer identity can be recovered without current-membership projection by propagating only unambiguous ticker-to-CIK identity already present inside the pinned PIT source.','identity_rule':'For each normalized ticker, propagate a CIK only if the pinned 2010-2025 PIT history associates that ticker with exactly one distinct non-null CIK. Never fill ambiguous/reused tickers and never use current-only external membership. This is identity lineage only, not a market feature.','snapshot_dates':rows,'historical_unique_tickers':len(all_hist_tickers),'source_native_unambiguous_tickers':len(unambiguous),'source_native_ambiguous_tickers':len(ambiguous),'historical_resolved_ticker_fraction':hist_cov,'ambiguous_ticker_fraction':ambig_frac,'decision_rule':'PIT_NATIVE_LINEAGE_READY only if every fixed snapshot reaches >=95% CIK coverage after source-native unambiguous propagation, historical ticker identity coverage is >=90%, and ambiguous ticker fraction is <=1%. No dropping unresolved constituents.','decision':'PIT_NATIVE_LINEAGE_READY' if pass_gate else 'PIT_NATIVE_LINEAGE_NOT_READY','scientific_consequence':('The pinned PIT source itself contains enough unambiguous issuer lineage to cross the P404 identifier boundary without current-membership projection. Next test may join SEC filed-at-safe facts while retaining unresolved/ambiguous rows fail-closed.' if pass_gate else 'Source-native ticker lineage is insufficient to clear P404. Keep the SEC alpha chain blocked on identifier representation and seek an independent historical identifier source; do not silently drop unresolved constituents or infer model failure.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p408_pit_native_cik_lineage_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'historical_resolved_ticker_fraction':round(hist_cov,4),'ambiguous_ticker_fraction':round(ambig_frac,4),'snapshots':{r['as_of']:round(r['final_cik_coverage'],4) for r in rows}},sort_keys=True))
