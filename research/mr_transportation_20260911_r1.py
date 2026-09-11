from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['IYT','XTN','XLI','SPY']; START='2011-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_transportation_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
        for s in ['IYT','XTN']:
            out[s+'_minus_XLI_pp']=100*(out[s]['cagr']-out['XLI']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2012+':frame('2012-01-01'),'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2012_2015':frame('2012-01-01','2015-12-31'),'2016_2019':frame('2016-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_XLI_pp',-999)>0 for v in src.values())
iw,ib=count('IYT',windows),count('IYT',blocks); xw,xb=count('XTN',windows),count('XTN',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('IYT_minus_XLI_pp',-999)>0 and windows['2022+'].get('XTN_minus_XLI_pp',-999)>0
passed=coverage and iw>=3 and ib>=3 and xw>=3 and xb>=3 and recent
out={'schema':'research.mr_transportation_20260911_r1.v1','workload_id':'MR_TRANSPORTATION_20260911_R1','parent':'TRANSPORTATION_INDUSTRY_SELECTION','claim':'If transportation specialization creates durable industrial-sector excess return, both IYT and equal-weighted XTN should beat broad industrials XLI after fixed endpoint costs across long windows and disjoint chronology; SPY is opportunity-cost context.','contract':{'implementations':['IYT','XTN'],'matched_control':'XLI','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'IYT_positive_windows':iw,'IYT_positive_blocks':ib,'XTN_positive_windows':xw,'XTN_positive_blocks':xb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLI in >=3/4 fixed windows and >=3/4 blocks, both beat XLI from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('TRANSPORTATION_SELECTION_SUPPORTED' if passed else ('TRANSPORTATION_SOURCE_COVERAGE_NOT_READY' if not coverage else 'TRANSPORTATION_SELECTION_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'IYT_XLI_pp':{k:round(v.get('IYT_minus_XLI_pp',-999),3) for k,v in windows.items()},'XTN_XLI_pp':{k:round(v.get('XTN_minus_XLI_pp',-999),3) for k,v in windows.items()},'XTN_SPY_pp':{k:round(v.get('XTN_minus_SPY_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
