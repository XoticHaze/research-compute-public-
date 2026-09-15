from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['ITB','XHB','XLY','SPY']; START='2009-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_homebuilders_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
        for s in ['ITB','XHB']:
            out[s+'_minus_XLY_pp']=100*(out[s]['cagr']-out['XLY']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2010+':frame('2010-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2010_2013':frame('2010-01-01','2013-12-31'),'2014_2017':frame('2014-01-01','2017-12-31'),'2018_2021':frame('2018-01-01','2021-12-31'),'2022_plus':frame('2022-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_XLY_pp',-999)>0 for v in src.values())
iw,ib=count('ITB',windows),count('ITB',blocks); xw,xb=count('XHB',windows),count('XHB',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('ITB_minus_XLY_pp',-999)>0 and windows['2022+'].get('XHB_minus_XLY_pp',-999)>0
passed=coverage and iw>=3 and ib>=3 and xw>=3 and xb>=3 and recent
out={'schema':'research.mr_homebuilders_20260911_r1.v1','workload_id':'MR_HOMEBUILDERS_20260911_R1','parent':'HOMEBUILDER_INDUSTRY_PREMIUM','claim':'If homebuilder specialization creates durable industry excess rather than simply consumer-discretionary beta, both ITB and XHB should beat XLY after fixed endpoint costs across long windows and disjoint chronology; SPY is opportunity-cost context.','contract':{'implementations':['ITB','XHB'],'matched_control':'XLY','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'ITB_positive_windows':iw,'ITB_positive_blocks':ib,'XHB_positive_windows':xw,'XHB_positive_blocks':xb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLY in >=3/4 fixed windows and >=3/4 blocks, both beat XLY from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('HOMEBUILDER_PREMIUM_SUPPORTED' if passed else ('HOMEBUILDER_SOURCE_COVERAGE_NOT_READY' if not coverage else 'HOMEBUILDER_PREMIUM_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'ITB_XLY_pp':{k:round(v.get('ITB_minus_XLY_pp',-999),3) for k,v in windows.items()},'XHB_XLY_pp':{k:round(v.get('XHB_minus_XLY_pp',-999),3) for k,v in windows.items()},'ITB_SPY_pp':{k:round(v.get('ITB_minus_SPY_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
