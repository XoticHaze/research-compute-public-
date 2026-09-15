from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['AMLP','MLPA','XLE','SPY']; START='2011-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_mlp_midstream_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1
    sh=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sh)}

def frame(start,end=None):
    out={s:stats(s,start,end) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        for s in ['AMLP','MLPA']:
            out[s+'_minus_XLE_pp']=100*(out[s]['cagr']-out['XLE']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2012+':frame('2012-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2012_2015':frame('2012-01-01','2015-12-31'),'2016_2019':frame('2016-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src): return sum(v.get(sym+'_minus_XLE_pp',-999)>0 for v in src.values())
aw,ab=count('AMLP',windows),count('AMLP',blocks); mw,mb=count('MLPA',windows),count('MLPA',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('AMLP_minus_XLE_pp',-999)>0 and windows['2022+'].get('MLPA_minus_XLE_pp',-999)>0
passed=coverage and aw>=3 and ab>=3 and mw>=3 and mb>=3 and recent
out={'schema':'research.mr_mlp_midstream_20260911_r1.v1','workload_id':'MR_MLP_MIDSTREAM_20260911_R1','parent':'MLP_MIDSTREAM_CASHFLOW_SELECTION','claim':'If listed midstream/MLP cash-flow exposure creates a durable industry premium rather than merely energy beta, both AMLP and MLPA should beat broad energy XLE after fixed endpoint costs across long windows and disjoint chronology; SPY is opportunity context.','contract':{'implementations':['AMLP','MLPA'],'matched_control':'XLE','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'AMLP_positive_windows':aw,'AMLP_positive_blocks':ab,'MLPA_positive_windows':mw,'MLPA_positive_blocks':mb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLE in >=3/4 fixed windows and >=3/4 disjoint blocks, both beat XLE in 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('MLP_MIDSTREAM_PREMIUM_SUPPORTED' if passed else ('MLP_MIDSTREAM_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MLP_MIDSTREAM_PREMIUM_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'AMLP_windows_XLE_pp':{k:round(v.get('AMLP_minus_XLE_pp',-999),3) for k,v in windows.items()},'MLPA_windows_XLE_pp':{k:round(v.get('MLPA_minus_XLE_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
