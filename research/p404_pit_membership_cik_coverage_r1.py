from __future__ import annotations
import json
from pathlib import Path
import pitindex
DATES=['2010-12-31','2015-12-31','2020-12-31','2025-12-31']
rows=[]
for d in DATES:
 df=pitindex.get_constituents(d,index='sp500')
 cik=df['cik'] if 'cik' in df.columns else []
 present=sum((x is not None and str(x).strip() not in ('','nan','None','<NA>')) for x in cik)
 n=len(df); cov=present/n if n else 0.0
 rows.append({'as_of':d,'members':n,'cik_present':present,'cik_coverage':cov})
h=pitindex.get_constituents_history('2010-01-01','2025-12-31',index='sp500')
# Historical names/tickers that appear in sparse PIT states, with CIK coverage measured without forward-filling identity.
uniq=h[['ticker','cik']].drop_duplicates() if 'cik' in h.columns else h[['ticker']].drop_duplicates().assign(cik=None)
all_tickers=uniq['ticker'].nunique(); with_cik=uniq.dropna(subset=['cik'])['ticker'].nunique(); hist_cov=with_cik/all_tickers if all_tickers else 0.0
min_snap=min(r['cik_coverage'] for r in rows)
pass_gate=min_snap>=0.95 and hist_cov>=0.90
out={'schema':'research.p404_pit_membership_cik_coverage.v1','workload_id':'P404_PIT_MEMBERSHIP_CIK_COVERAGE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'The pinned point-in-time S&P 500 membership source carries enough contemporaneous issuer CIK identity to join SEC filed-at-safe facts without projecting current membership or silently dropping historical constituents.','source':'pitindex','source_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','snapshot_dates':rows,'historical_unique_tickers':int(all_tickers),'historical_unique_tickers_with_cik':int(with_cik),'historical_ticker_cik_coverage':hist_cov,'decision_rule':'JOIN_READY only if each fixed snapshot has >=95% CIK coverage and unique historical ticker CIK coverage over 2010-2025 is >=90%. Missing identity is a data/representation blocker, not model failure. No ticker/date/universe dropping after observation.','decision':'PIT_MEMBERSHIP_SEC_JOIN_READY' if pass_gate else 'PIT_MEMBERSHIP_SEC_JOIN_NOT_READY','scientific_consequence':('Historical membership identity is sufficiently complete for a first causally joined SEC cross-sectional discriminator, subject to filed_at and issuer-lineage guards.' if pass_gate else 'Do not run constituent-level SEC alpha selection by silently dropping missing CIKs. Quantify and resolve historical issuer identity/lineage first; this is DATA/REPRESENTATION failure, not fundamental-model failure.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p404_pit_membership_cik_coverage_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':out['decision'],'snapshots':{r['as_of']:round(r['cik_coverage'],4) for r in rows},'historical_ticker_cik_coverage':round(hist_cov,4)},sort_keys=True))
