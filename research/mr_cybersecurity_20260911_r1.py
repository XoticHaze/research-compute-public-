from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['HACK','CIBR','QQQ','SPY']; START='2015-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_cybersecurity_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
        for s in ['HACK','CIBR']:
            out[s+'_minus_QQQ_pp']=100*(out[s]['cagr']-out['QQQ']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2016+':frame('2016-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2016_2018':frame('2016-01-01','2018-12-31'),'2019_2021':frame('2019-01-01','2021-12-31'),'2022_2024':frame('2022-01-01','2024-12-31'),'2025_plus':frame('2025-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_QQQ_pp',-999)>0 for v in src.values())
hw,hb=count('HACK',windows),count('HACK',blocks); cw,cb=count('CIBR',windows),count('CIBR',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('HACK_minus_QQQ_pp',-999)>0 and windows['2022+'].get('CIBR_minus_QQQ_pp',-999)>0
passed=coverage and hw>=3 and hb>=3 and cw>=3 and cb>=3 and recent
out={'schema':'research.mr_cybersecurity_20260911_r1.v1','workload_id':'MR_CYBERSECURITY_20260911_R1','parent':'CYBERSECURITY_INDUSTRY_SELECTION','claim':'If cybersecurity specialization creates durable alpha beyond generic technology growth beta, both HACK and CIBR should beat QQQ after fixed endpoint costs across long windows and disjoint chronology; SPY is broad-market opportunity context.','contract':{'implementations':['HACK','CIBR'],'matched_control':'QQQ','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'HACK_positive_windows':hw,'HACK_positive_blocks':hb,'CIBR_positive_windows':cw,'CIBR_positive_blocks':cb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat QQQ in >=3/4 fixed windows and >=3/4 blocks, both beat QQQ from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('CYBERSECURITY_SELECTION_SUPPORTED' if passed else ('CYBERSECURITY_SOURCE_COVERAGE_NOT_READY' if not coverage else 'CYBERSECURITY_SELECTION_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'HACK_QQQ_pp':{k:round(v.get('HACK_minus_QQQ_pp',-999),3) for k,v in windows.items()},'CIBR_QQQ_pp':{k:round(v.get('CIBR_minus_QQQ_pp',-999),3) for k,v in windows.items()},'CIBR_SPY_pp':{k:round(v.get('CIBR_minus_SPY_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
