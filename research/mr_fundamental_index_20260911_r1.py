from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

CANDS=['PRF','FNDB']; T=CANDS+['VTI','SPY']; START='2012-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_fundamental_index_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,a,b=None):
    s=px[sym].loc[a:b].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425; gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2); cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1; sd=r.std(ddof=1)
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float((r.mean()/sd)*math.sqrt(252)) if sd>0 else None}

def frame(a,b=None):
    out={s:stats(s,a,b) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        for c in CANDS:
            out[c+'_minus_VTI_pp']=100*(out[c]['cagr']-out['VTI']['cagr']); out[c+'_minus_SPY_pp']=100*(out[c]['cagr']-out['SPY']['cagr'])
    return out
windows={'2014+':frame('2014-01-01'),'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2014_2016':frame('2014-01-01','2016-12-31'),'2017_2019':frame('2017-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def cnt(c,src):return sum(v.get(c+'_minus_VTI_pp',-999)>0 for v in src.values())
counts={c:{'positive_windows':cnt(c,windows),'positive_blocks':cnt(c,blocks)} for c in CANDS}
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=all(windows['2022+'].get(c+'_minus_VTI_pp',-999)>0 for c in CANDS)
passed=coverage and recent and all(counts[c]['positive_windows']>=3 and counts[c]['positive_blocks']>=3 for c in CANDS)
decision='FUNDAMENTAL_INDEX_PREMIUM_SUPPORTED' if passed else ('FUNDAMENTAL_INDEX_SOURCE_COVERAGE_NOT_READY' if not coverage else 'FUNDAMENTAL_INDEX_PREMIUM_NOT_SUPPORTED')
out={'schema':'research.mr_fundamental_index_20260911_r1.v1','workload_id':'MR_FUNDAMENTAL_INDEX_20260911_R1','parent':'FUNDAMENTAL_INDEX_WEIGHTING_PREMIUM','claim':'If fundamentals-weighted broad-US indexing creates durable excess rather than wrapper-specific style drift, both PRF and FNDB should beat total-market VTI after equal fixed endpoint costs across fixed windows and disjoint chronology, with SPY as opportunity context.','contract':{'implementations':CANDS,'matched_control':'VTI','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':counts,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat VTI after equal costs in >=3/4 fixed windows and >=3/4 chronology blocks and both are positive from 2022+. No product/control/date/cost rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'counts':counts,'VTI_pp':{c:{k:round(v.get(c+'_minus_VTI_pp',-999),3) for k,v in windows.items()} for c in CANDS},'SPY_pp_2014+':{c:round(windows['2014+'].get(c+'_minus_SPY_pp',-999),3) for c in CANDS}},sort_keys=True))
