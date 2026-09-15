from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

CANDS=['DBMF','KMLM']; T=CANDS+['BIL','SPY']; START='2018-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_managed_futures_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px.resample('ME').last().pct_change().dropna(how='all')

def stats(r,cost=0.0):
    r=r.dropna()
    if len(r)<12:return {'months':int(len(r))}
    w=(1+r).cumprod()*(1-cost)**2; years=len(r)/12.0; dd=w/w.cummax()-1; sd=r.std(ddof=1)
    return {'months':int(len(r)),'cagr':float(w.iloc[-1]**(1/years)-1),'maxdd':float(dd.min()),'sharpe':float((r.mean()/sd)*math.sqrt(12)) if sd>0 else None}

def ev(c,a,b=None):
    z=m[[c,'BIL','SPY']].loc[a:b].dropna(); cs=stats(z[c],EP); bil=stats(z['BIL']); spy=stats(z['SPY'])
    out={'candidate':cs,'cash_control':bil,'spy_opportunity':spy}
    if cs.get('months',0)>=12:
        out['cash_excess_cagr_pp']=100*(cs['cagr']-bil['cagr']); out['spy_excess_cagr_pp']=100*(cs['cagr']-spy['cagr']); out['spy_corr']=float(z[c].corr(z['SPY']))
    return out
windows={'2021+':('2021-01-01',None),'2022+':('2022-01-01',None),'2023+':('2023-01-01',None),'2024+':('2024-01-01',None)}
blocks={'2021_2022':('2021-01-01','2022-12-31'),'2023_2024':('2023-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
res={'windows':{},'blocks':{}}
for k,(a,b) in windows.items():res['windows'][k]={c:ev(c,a,b) for c in CANDS}
for k,(a,b) in blocks.items():res['blocks'][k]={c:ev(c,a,b) for c in CANDS}
def cnt(kind,c):return sum(v[c].get('cash_excess_cagr_pp',-999)>0 for v in res[kind].values())
counts={c:{'positive_windows':cnt('windows',c),'positive_blocks':cnt('blocks',c)} for c in CANDS}
coverage=all(v[c]['candidate'].get('months',0)>=12 for v in res['blocks'].values() for c in CANDS)
recent=all(res['windows']['2024+'][c].get('cash_excess_cagr_pp',-999)>0 for c in CANDS)
lowcorr=all(abs(res['windows']['2021+'][c].get('spy_corr',999))<=0.35 for c in CANDS)
passed=coverage and recent and lowcorr and all(counts[c]['positive_windows']>=3 and counts[c]['positive_blocks']>=2 for c in CANDS)
decision='MANAGED_FUTURES_PREMIUM_SUPPORTED' if passed else ('MANAGED_FUTURES_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MANAGED_FUTURES_PREMIUM_NOT_SUPPORTED')
out={'schema':'research.mr_managed_futures_20260911_r1.v1','workload_id':'MR_MANAGED_FUTURES_20260911_R1','parent':'MANAGED_FUTURES_DIVERSIFYING_PREMIUM','claim':'If liquid managed-futures trend/carry implementations create durable diversifying excess rather than one-off crisis gains, both DBMF and KMLM should beat BIL after fixed endpoint costs across fixed recent windows and disjoint chronology while retaining low correlation to SPY.','contract':{'implementations':CANDS,'matched_control':'BIL cash hurdle','opportunity_control':'SPY','candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks),'max_abs_spy_corr':0.35},**res,'counts':counts,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat BIL after costs in >=3/4 fixed windows and >=2/3 chronology blocks, both beat BIL from 2024+, both have |monthly correlation to SPY| <=0.35 from 2021+, and every block has >=12 months. No product/date/cost/correlation rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'counts':counts,'2021+':{c:{'cash_excess_pp':round(res['windows']['2021+'][c].get('cash_excess_cagr_pp',-999),3),'spy_excess_pp':round(res['windows']['2021+'][c].get('spy_excess_cagr_pp',-999),3),'spy_corr':round(res['windows']['2021+'][c].get('spy_corr',999),3)} for c in CANDS},'2024+':{c:round(res['windows']['2024+'][c].get('cash_excess_cagr_pp',-999),3) for c in CANDS}},sort_keys=True))
